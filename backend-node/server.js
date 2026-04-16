import express from "express";
import cors from "cors";
import { MongoClient, ObjectId } from "mongodb";
import { v4 as uuidv4 } from "uuid";
import "dotenv/config";

const app = express();
const PORT = process.env.PORT || 3001;
const PYTHON_API = process.env.PYTHON_API_URL || "http://localhost:8000";
const MONGODB_URI = process.env.MONGODB_URI || "";

// ── Middleware ────────────────────────────────────────────────────────────

app.use(cors({ origin: true, credentials: true }));
app.use(express.json());

// ── MongoDB connection ───────────────────────────────────────────────────

let db = null;

async function connectDB() {
  if (!MONGODB_URI) {
    console.warn("[DB] No MONGODB_URI set - running without persistence");
    return;
  }
  try {
    const client = new MongoClient(MONGODB_URI);
    await client.connect();
    db = client.db("curalink");
    console.log("[DB] Connected to MongoDB Atlas");
  } catch (err) {
    console.error("[DB] Connection failed:", err.message);
  }
}

// ── Session management ───────────────────────────────────────────────────

app.post("/api/sessions", async (req, res) => {
  const sessionId = uuidv4();
  const session = {
    session_id: sessionId,
    created_at: new Date(),
    disease: req.body.disease || "",
    location: req.body.location || "",
    patient_name: req.body.patient_name || "",
  };

  if (db) {
    try {
      await db.collection("sessions").insertOne(session);
    } catch (err) {
      console.error("[Sessions] Create failed:", err.message);
    }
  }

  res.json({ session_id: sessionId, ...session });
});

app.get("/api/sessions/:sessionId", async (req, res) => {
  const { sessionId } = req.params;

  if (!db) return res.json({ session_id: sessionId, messages: [] });

  try {
    const session = await db
      .collection("sessions")
      .findOne({ session_id: sessionId });
    const messages = await db
      .collection("messages")
      .find({ session_id: sessionId })
      .sort({ created_at: 1 })
      .toArray();

    res.json({
      session_id: sessionId,
      disease: session?.disease || "",
      location: session?.location || "",
      messages: messages.map((m) => ({
        id: m._id.toString(),
        role: m.role,
        content: m.content,
        publications: m.publications || [],
        trials: m.trials || [],
        sources_count: m.sources_count || 0,
        processing_time: m.processing_time || 0,
        created_at: m.created_at,
      })),
    });
  } catch (err) {
    console.error("[Sessions] Get failed:", err.message);
    res.json({ session_id: sessionId, messages: [] });
  }
});

// ── Chat endpoint (proxies to Python pipeline) ───────────────────────────

app.post("/api/chat", async (req, res) => {
  const { message, disease, location, session_id } = req.body;

  if (!message) {
    return res.status(400).json({ error: "Message is required" });
  }

  const sessionId = session_id || uuidv4();

  // Save user message to MongoDB
  if (db) {
    try {
      await db.collection("messages").insertOne({
        session_id: sessionId,
        role: "user",
        content: message,
        created_at: new Date(),
      });
    } catch (err) {
      console.error("[Chat] Save user msg failed:", err.message);
    }
  }

  try {
    // Forward to Python FastAPI pipeline
    const response = await fetch(`${PYTHON_API}/chat`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        disease: disease || "",
        location: location || "",
        session_id: sessionId,
      }),
    });

    if (!response.ok) {
      const errText = await response.text();
      throw new Error(`Pipeline returned ${response.status}: ${errText}`);
    }

    const data = await response.json();

    // Save assistant response to MongoDB
    if (db) {
      try {
        await db.collection("messages").insertOne({
          session_id: sessionId,
          role: "assistant",
          content: data.content,
          publications: data.publications || [],
          trials: data.trials || [],
          sources_count: data.sources_count || 0,
          processing_time: data.processing_time || 0,
          created_at: new Date(),
        });
      } catch (err) {
        console.error("[Chat] Save assistant msg failed:", err.message);
      }
    }

    res.json({
      session_id: sessionId,
      content: data.content,
      publications: data.publications || [],
      trials: data.trials || [],
      sources_count: data.sources_count || 0,
      processing_time: data.processing_time || 0,
    });
  } catch (err) {
    console.error("[Chat] Pipeline error:", err.message);
    res.status(500).json({
      error: "Failed to process your query. Please try again.",
      details: err.message,
    });
  }
});

// ── Stream endpoint (SSE proxy) ──────────────────────────────────────────

// STEP 2: Replace the /api/chat/stream route in backend-node/server.js with this

app.post("/api/chat/stream", async (req, res) => {
  const { message, disease, location, session_id } = req.body;
  const sessionId = session_id || uuidv4();

  res.setHeader("Content-Type", "text/event-stream");
  res.setHeader("Cache-Control", "no-cache");
  res.setHeader("Connection", "keep-alive");
  res.setHeader("X-Accel-Buffering", "no");
  res.flushHeaders();

  // Save user message
  if (db) {
    try {
      await db.collection("messages").insertOne({
        session_id: sessionId,
        role: "user",
        content: message,
        created_at: new Date(),
      });
    } catch (err) {
      console.error("[Stream] Save user msg failed:", err.message);
    }
  }

  let finalResponse = null;

  try {
    const pythonResp = await fetch(`${PYTHON_API}/chat/stream`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ message, disease, location, session_id: sessionId }),
    });

    const reader = pythonResp.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    while (true) {
      const { done, value } = await reader.read();
      if (done) break;

      const chunk = decoder.decode(value, { stream: true });
      buffer += chunk;

      // Forward chunk to client immediately
      res.write(chunk);

      // Parse events to catch the final response payload for saving
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";

      for (const line of lines) {
        if (!line.startsWith("data: ") || line.includes("[DONE]")) continue;
        try {
          const data = JSON.parse(line.slice(6));
          if (data.type === "response") {
            finalResponse = data;
          }
        } catch { }
      }
    }

    // Save final assistant message to DB
    if (db && finalResponse) {
      try {
        await db.collection("messages").insertOne({
          session_id: sessionId,
          role: "assistant",
          content: finalResponse.content,
          publications: finalResponse.publications || [],
          trials: finalResponse.trials || [],
          sources_count: finalResponse.sources_count || 0,
          processing_time: finalResponse.processing_time || 0,
          created_at: new Date(),
        });
      } catch (err) {
        console.error("[Stream] Save assistant msg failed:", err.message);
      }
    }
  } catch (err) {
    res.write(`data: ${JSON.stringify({ type: "error", message: err.message })}\n\n`);
  }

  res.end();
});

// ── Conversation history ─────────────────────────────────────────────────

app.delete("/api/sessions/:sessionId", async (req, res) => {
  const { sessionId } = req.params;
  if (db) {
    await db.collection("messages").deleteMany({ session_id: sessionId });
    await db.collection("sessions").deleteOne({ session_id: sessionId });
  }

  // Also clear Python-side cache
  try {
    await fetch(`${PYTHON_API}/conversations/${sessionId}`, {
      method: "DELETE",
    });
  } catch { }

  res.json({ status: "cleared" });
});

// ── Health check ─────────────────────────────────────────────────────────

app.get("/api/health", async (req, res) => {
  let pythonStatus = "unknown";
  try {
    const pyResp = await fetch(`${PYTHON_API}/health`);
    pythonStatus = pyResp.ok ? "ok" : "error";
  } catch {
    pythonStatus = "unreachable";
  }

  res.json({
    status: "ok",
    service: "curalink-gateway",
    python_pipeline: pythonStatus,
    database: db ? "connected" : "disconnected",
  });
});

// ── Start server ─────────────────────────────────────────────────────────

connectDB().then(() => {
  app.listen(PORT, () => {
    console.log(`[Curalink API] Gateway running on port ${PORT}`);
    console.log(`[Curalink API] Python pipeline at ${PYTHON_API}`);
  });
});
