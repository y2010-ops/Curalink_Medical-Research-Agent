const API_BASE = import.meta.env.VITE_API_URL || "/api";

export async function createSession({ disease, location, patientName }) {
  const res = await fetch(`${API_BASE}/sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      disease,
      location,
      patient_name: patientName,
    }),
  });
  return res.json();
}

export async function sendMessage({ message, disease, location, sessionId }) {
  const res = await fetch(`${API_BASE}/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      disease: disease || "",
      location: location || "",
      session_id: sessionId || "default",
    }),
  });

  if (!res.ok) {
    const err = await res.json().catch(() => ({ error: "Unknown error" }));
    throw new Error(err.error || err.detail || `Request failed: ${res.status}`);
  }

  return res.json();
}

export async function getSession(sessionId) {
  const res = await fetch(`${API_BASE}/sessions/${sessionId}`);
  return res.json();
}

export async function clearSession(sessionId) {
  await fetch(`${API_BASE}/sessions/${sessionId}`, { method: "DELETE" });
}

export async function checkHealth() {
  try {
    const res = await fetch(`${API_BASE}/health`);
    return res.json();
  } catch {
    return { status: "error" };
  }
}

export async function streamMessage({ message, disease, location, sessionId }, { onStage, onResponse, onError }) {
  const res = await fetch(`${API_BASE}/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      message,
      disease: disease || "",
      location: location || "",
      session_id: sessionId || "default",
    }),
  });

  if (!res.ok) {
    onError?.(`Server returned ${res.status}`);
    return;
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() || "";

    for (const line of lines) {
      if (!line.startsWith("data: ")) continue;
      const payload = line.slice(6).trim();
      if (payload === "[DONE]") return;

      try {
        const data = JSON.parse(payload);
        if (data.type === "stage") {
          onStage?.(data);
        } else if (data.type === "response") {
          onResponse?.(data);
        } else if (data.type === "error") {
          onError?.(data.message);
        }
      } catch (err) {
        console.warn("Failed to parse SSE chunk:", payload);
      }
    }
  }
}
