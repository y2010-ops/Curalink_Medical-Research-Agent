import { useState, useCallback } from "react";
import Onboarding from "./components/Onboarding.jsx";
import ChatInterface from "./components/ChatInterface.jsx";
import { createSession } from "./utils/api.js";

export default function App() {
  const [session, setSession] = useState(null);
  const [loading, setLoading] = useState(false);

  const handleOnboardingComplete = useCallback(async (data) => {
    setLoading(true);
    try {
      const sess = await createSession(data);
      setSession({ ...sess, ...data });
    } catch (err) {
      console.error("Failed to create session:", err);
      // Fallback: create a local session
      setSession({
        session_id: crypto.randomUUID(),
        ...data,
      });
    } finally {
      setLoading(false);
    }
  }, []);

  const handleNewSession = useCallback(() => {
    setSession(null);
  }, []);

  return (
    <div className="min-h-screen bg-cura-950 flex flex-col">
      {!session ? (
        <Onboarding onComplete={handleOnboardingComplete} loading={loading} />
      ) : (
        <ChatInterface session={session} onNewSession={handleNewSession} />
      )}
    </div>
  );
}
