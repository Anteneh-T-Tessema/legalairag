import { useState, useRef, useEffect } from "react";
import { ask } from "../api/client";
import type { ChatMessage } from "../api/client";

interface Props {
  jurisdiction?: string;
}

export function ChatInterface({ jurisdiction }: Props) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    const text = input.trim();
    if (text.length < 3 || loading) return;

    const userMsg: ChatMessage = {
      role: "user",
      content: text,
      timestamp: Date.now(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setLoading(true);

    try {
      const res = await ask(text, jurisdiction || undefined);
      const assistantMsg: ChatMessage = {
        role: "assistant",
        content: res.answer,
        sources: res.source_ids,
        citations: res.citations,
        confidence: res.confidence,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, assistantMsg]);
    } catch (e) {
      const errorMsg: ChatMessage = {
        role: "assistant",
        content: `Error: ${e instanceof Error ? e.message : "Unknown error"}`,
        timestamp: Date.now(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="chat-interface">
      <div className="chat-messages">
        {messages.length === 0 && (
          <div className="chat-empty">
            <h3>Indiana Legal Research Chat</h3>
            <p>Ask questions about Indiana law, court procedures, or case precedents.</p>
            <div className="chat-suggestions">
              <button onClick={() => setInput("What are the filing deadlines for small claims in Indiana?")}>
                Filing deadlines for small claims?
              </button>
              <button onClick={() => setInput("What constitutes self-defense under Indiana Code?")}>
                Self-defense under Indiana Code?
              </button>
              <button onClick={() => setInput("Explain Indiana eviction notice requirements")}>
                Indiana eviction notice requirements
              </button>
            </div>
          </div>
        )}
        {messages.map((msg, i) => (
          <div key={i} className={`chat-message chat-message--${msg.role}`}>
            <div className="chat-message-content">
              {msg.content}
              {msg.citations && msg.citations.length > 0 && (
                <div className="chat-citations">
                  {msg.citations.map((c) => (
                    <span key={c} className="citation-tag">{c}</span>
                  ))}
                </div>
              )}
              {msg.confidence && (
                <span className={`confidence-indicator confidence--${msg.confidence.toLowerCase()}`}>
                  {msg.confidence} confidence
                </span>
              )}
            </div>
          </div>
        ))}
        {loading && (
          <div className="chat-message chat-message--assistant">
            <div className="chat-message-content chat-typing">
              Researching…
            </div>
          </div>
        )}
        <div ref={bottomRef} />
      </div>
      <div className="chat-input">
        <textarea
          rows={2}
          placeholder="Ask a legal question..."
          value={input}
          onChange={(e) => setInput(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter" && !e.shiftKey) {
              e.preventDefault();
              handleSend();
            }
          }}
          disabled={loading}
        />
        <button onClick={handleSend} disabled={loading || input.trim().length < 3}>
          Send
        </button>
      </div>
    </div>
  );
}
