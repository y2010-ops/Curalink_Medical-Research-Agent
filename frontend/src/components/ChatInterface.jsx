import { useState, useRef, useEffect, useCallback } from "react";
import {
  Send,
  Sparkles,
  RotateCcw,
  Clock,
  BookOpen,
  FlaskConical,
  ChevronDown,
  ChevronUp,
  ExternalLink,
  Loader2,
  AlertCircle,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { sendMessage, clearSession, streamMessage } from "../utils/api.js";
import SourceCard from "./SourceCard.jsx";
import PipelineProgress from "./PipelineProgress.jsx";

export default function ChatInterface({ session, onNewSession }) {
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [statusMsg, setStatusMsg] = useState("");
  const [error, setError] = useState(null);
  const messagesEndRef = useRef(null);
  const inputRef = useRef(null);
  const [currentStage, setCurrentStage] = useState(null);
  const [stageDetail, setStageDetail] = useState(null);
  const [stageStartTime, setStageStartTime] = useState(0);
  const [elapsed, setElapsed] = useState(0);

  // Auto-scroll to bottom
  useEffect(() => {
    if (!isLoading || !stageStartTime) {
      setElapsed(0);
      return;
    }
    const interval = setInterval(() => {
      setElapsed((Date.now() - stageStartTime) / 1000);
    }, 100);
    return () => clearInterval(interval);
  }, [isLoading, stageStartTime]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, isLoading]);

  // Focus input on load
  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  // Add welcome message on mount
  useEffect(() => {
    const name = session.patientName ? `, ${session.patientName}` : "";
    setMessages([
      {
        id: "welcome",
        role: "assistant",
        content: `Welcome${name}! I'm Curalink, your medical research assistant.\n\nI'll help you explore the latest research publications and clinical trials related to **${session.disease}**${session.location ? ` in **${session.location}**` : ""}.\n\nWhat would you like to know? You can ask about treatments, recent studies, clinical trials, or anything related to your condition.`,
        publications: [],
        trials: [],
      },
    ]);
  }, [session]);

  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || isLoading) return;

    setInput("");
    setError(null);

    // Add user message immediately
    const userMsg = {
      id: `user-${Date.now()}`,
      role: "user",
      content: text,
    };
    setMessages((prev) => [...prev, userMsg]);

    // Start loading with first stage
    setIsLoading(true);
    setCurrentStage("router");
    setStageDetail(null);
    setStageStartTime(Date.now());

    try {
      await streamMessage(
        {
          message: text,
          disease: session.disease,
          location: session.location,
          sessionId: session.session_id,
        },
        {
          onStage: ({ stage, message, detail }) => {
            setCurrentStage(stage);
            setStageDetail(detail || message || null);
          },
          onResponse: (data) => {
            const assistantMsg = {
              id: `asst-${Date.now()}`,
              role: "assistant",
              content: data.content,
              publications: data.publications || [],
              trials: data.trials || [],
              sourcesCount: data.sources_count || 0,
              processingTime: data.processing_time || 0,
            };
            setMessages((prev) => [...prev, assistantMsg]);
          },
          onError: (err) => {
            setError(err);
            setMessages((prev) => [
              ...prev,
              {
                id: `err-${Date.now()}`,
                role: "assistant",
                content: "I'm sorry, I encountered an error processing your request. Please try again.",
                isError: true,
              },
            ]);
          },
        }
      );
    } catch (err) {
      console.error("Stream failed:", err);
      setError(err.message);
    } finally {
      setIsLoading(false);
      setCurrentStage(null);
      setStageDetail(null);
      setStageStartTime(0);
    }
  }, [input, isLoading, session]);

  const handleKeyDown = (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handleClear = async () => {
    try {
      await clearSession(session.session_id);
    } catch { }
    onNewSession();
  };

  const suggestedQueries = [
    `Latest treatments for ${session.disease}`,
    `Clinical trials for ${session.disease}`,
    `Recent research breakthroughs in ${session.disease}`,
    `Top researchers studying ${session.disease}`,
  ];

  return (
    <div className="flex-1 flex flex-col h-screen">
      {/* Header */}
      <header className="flex-shrink-0 border-b border-cura-800/50 bg-cura-950/80 backdrop-blur-sm px-4 py-3">
        <div className="max-w-3xl mx-auto flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <div className="w-8 h-8 rounded-lg bg-cura-600 flex items-center justify-center">
              <Sparkles className="w-4 h-4 text-cura-100" />
            </div>
            <div>
              <h1 className="font-display text-lg font-semibold text-cura-50 leading-tight">
                Curalink
              </h1>
              <p className="text-[11px] text-cura-500 leading-tight">
                {session.disease}
                {session.location && ` · ${session.location}`}
              </p>
            </div>
          </div>
          <button
            onClick={handleClear}
            className="flex items-center gap-1.5 px-3 py-1.5 text-xs text-cura-500 hover:text-cura-300 border border-cura-800 hover:border-cura-600 rounded-lg transition-all"
          >
            <RotateCcw className="w-3 h-3" />
            New Session
          </button>
        </div>
      </header>

      {/* Messages Area */}
      <main className="flex-1 overflow-y-auto px-4 py-6">
        <div className="max-w-3xl mx-auto space-y-6">
          {messages.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}

          {/* Loading indicator */}
          {isLoading && (
            <PipelineProgress
              currentStage={currentStage}
              stageDetail={stageDetail}
              elapsed={elapsed}
            />
          )}

          {/* Suggested queries (show when no user messages yet) */}
          {messages.length <= 1 && !isLoading && (
            <div className="space-y-2 mt-4">
              <p className="text-xs text-cura-600 uppercase tracking-wider font-medium">
                Try asking
              </p>
              <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
                {suggestedQueries.map((q) => (
                  <button
                    key={q}
                    onClick={() => {
                      setInput(q);
                      inputRef.current?.focus();
                    }}
                    className="text-left px-3.5 py-2.5 text-sm text-cura-400 bg-cura-900/30 border border-cura-800/40 rounded-xl hover:bg-cura-900/60 hover:text-cura-300 hover:border-cura-700 transition-all"
                  >
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>
      </main>

      {/* Error banner */}
      {error && (
        <div className="flex-shrink-0 px-4 py-2 bg-red-950/50 border-t border-red-900/30">
          <div className="max-w-3xl mx-auto flex items-center gap-2 text-xs text-red-400">
            <AlertCircle className="w-3.5 h-3.5 flex-shrink-0" />
            {error}
          </div>
        </div>
      )}

      {/* Input Area */}
      <div className="flex-shrink-0 border-t border-cura-800/50 bg-cura-950/90 backdrop-blur-sm px-4 py-3">
        <div className="max-w-3xl mx-auto">
          <div className="flex items-end gap-2">
            <div className="flex-1 relative">
              <textarea
                ref={inputRef}
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleKeyDown}
                placeholder="Ask about treatments, research, clinical trials..."
                rows={1}
                className="w-full px-4 py-3 bg-cura-900/50 border border-cura-800 rounded-xl text-sm text-cura-50 placeholder:text-cura-700 focus:outline-none focus:border-cura-500 focus:ring-1 focus:ring-cura-500/20 resize-none transition-all"
                style={{
                  minHeight: "44px",
                  maxHeight: "120px",
                }}
                onInput={(e) => {
                  e.target.style.height = "auto";
                  e.target.style.height =
                    Math.min(e.target.scrollHeight, 120) + "px";
                }}
              />
            </div>
            <button
              onClick={handleSend}
              disabled={!input.trim() || isLoading}
              className="flex-shrink-0 w-11 h-11 flex items-center justify-center bg-cura-600 hover:bg-cura-500 disabled:bg-cura-800 disabled:text-cura-700 text-cura-50 rounded-xl transition-all"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
          <p className="text-[10px] text-cura-800 mt-1.5 text-center">
            Curalink provides research information only — not medical advice.
          </p>
        </div>
      </div>
    </div>
  );
}

// ── Message Bubble Component ──────────────────────────────────────────────

function MessageBubble({ message }) {
  const isUser = message.role === "user";
  const [sourcesOpen, setSourcesOpen] = useState(false);

  const hasSources =
    (message.publications?.length || 0) + (message.trials?.length || 0) > 0;

  return (
    <div
      className={`flex gap-3 message-enter ${isUser ? "justify-end" : ""}`}
    >
      {/* Avatar */}
      {!isUser && (
        <div className="w-7 h-7 rounded-lg bg-cura-700 flex items-center justify-center flex-shrink-0 mt-0.5">
          <Sparkles className="w-3.5 h-3.5 text-cura-300" />
        </div>
      )}

      <div className={`max-w-[85%] ${isUser ? "order-first" : ""}`}>
        {/* Bubble */}
        <div
          className={`rounded-2xl px-4 py-3 ${isUser
              ? "bg-cura-600 text-cura-50 rounded-tr-md"
              : message.isError
                ? "bg-red-950/30 border border-red-900/30 rounded-tl-md"
                : "bg-cura-900/50 border border-cura-800/50 rounded-tl-md"
            }`}
        >
          {isUser ? (
            <p className="text-sm leading-relaxed">{message.content}</p>
          ) : (
            <div className="markdown-content text-sm">
              <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.content}</ReactMarkdown>
            </div>
          )}
        </div>

        {/* Processing time + sources toggle */}
        {!isUser && (message.processingTime || hasSources) && (
          <div className="flex items-center gap-3 mt-1.5 px-1">
            {message.processingTime > 0 && (
              <span className="flex items-center gap-1 text-[11px] text-cura-700">
                <Clock className="w-3 h-3" />
                {message.processingTime.toFixed(1)}s
              </span>
            )}
            {message.sourcesCount > 0 && (
              <span className="text-[11px] text-cura-700">
                {message.sourcesCount} sources analyzed
              </span>
            )}
            {hasSources && (
              <button
                onClick={() => setSourcesOpen(!sourcesOpen)}
                className="flex items-center gap-1 text-[11px] text-cura-500 hover:text-cura-300 transition-colors ml-auto"
              >
                {sourcesOpen ? (
                  <>
                    Hide sources <ChevronUp className="w-3 h-3" />
                  </>
                ) : (
                  <>
                    View sources <ChevronDown className="w-3 h-3" />
                  </>
                )}
              </button>
            )}
          </div>
        )}

        {/* Expandable sources panel */}
        {sourcesOpen && hasSources && (
          <div className="mt-3 space-y-3 message-enter">
            {/* Publications */}
            {message.publications?.length > 0 && (
              <div>
                <h4 className="flex items-center gap-1.5 text-xs font-medium text-cura-500 uppercase tracking-wider mb-2">
                  <BookOpen className="w-3 h-3" />
                  Publications ({message.publications.length})
                </h4>
                <div className="space-y-2">
                  {message.publications.map((pub, i) => (
                    <SourceCard key={i} type="publication" data={pub} index={i + 1} />
                  ))}
                </div>
              </div>
            )}

            {/* Clinical Trials */}
            {message.trials?.length > 0 && (
              <div>
                <h4 className="flex items-center gap-1.5 text-xs font-medium text-cura-500 uppercase tracking-wider mb-2">
                  <FlaskConical className="w-3 h-3" />
                  Clinical Trials ({message.trials.length})
                </h4>
                <div className="space-y-2">
                  {message.trials.map((trial, i) => (
                    <SourceCard key={i} type="trial" data={trial} index={i + 1} />
                  ))}
                </div>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
