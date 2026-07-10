"use client";

import { useChat } from "ai/react";
import { useEffect, useRef, useState } from "react";

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  const { messages, input, handleInputChange, handleSubmit, isLoading, error } =
    useChat({ api: "/api/chat" });

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  return (
    <>
      {/* Floating toggle button */}
      <button
        onClick={() => setOpen((o) => !o)}
        className="fixed bottom-6 right-6 z-50 w-14 h-14 rounded-full bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg flex items-center justify-center text-2xl transition-colors"
        aria-label="Toggle chat"
      >
        {open ? "×" : "⚽"}
      </button>

      {/* Chat panel */}
      {open && (
        <div className="fixed bottom-24 right-6 z-50 w-80 sm:w-96 h-[500px] flex flex-col rounded-2xl border border-border bg-surface shadow-2xl overflow-hidden">
          {/* Header */}
          <div className="px-4 py-3 border-b border-border bg-surface">
            <p className="text-sm font-semibold text-white">Footy Oracle AI</p>
            <p className="text-xs text-gray-400">Ask about predictions, form, or accuracy</p>
          </div>

          {/* Messages */}
          <div className="flex-1 overflow-y-auto px-4 py-3 space-y-3">
            {messages.length === 0 && (
              <div className="space-y-2 pt-2">
                {[
                  "Who will win England vs France?",
                  "How accurate is the BTTS model?",
                  "What expert was used for Man City's prediction?",
                ].map((s) => (
                  <button
                    key={s}
                    onClick={() =>
                      handleSubmit(undefined, { data: { content: s } } as never)
                    }
                    className="w-full text-left text-xs px-3 py-2 rounded-lg border border-border text-gray-300 hover:bg-white/5 transition-colors"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}

            {messages.map((m) => (
              <div
                key={m.id}
                className={`flex ${m.role === "user" ? "justify-end" : "justify-start"}`}
              >
                <div
                  className={`max-w-[85%] rounded-xl px-3 py-2 text-sm whitespace-pre-wrap ${
                    m.role === "user"
                      ? "bg-indigo-600 text-white"
                      : "bg-white/10 text-gray-100"
                  }`}
                >
                  {m.content}
                </div>
              </div>
            ))}

            {isLoading && (
              <div className="flex justify-start">
                <div className="bg-white/10 rounded-xl px-3 py-2 text-sm text-gray-400 animate-pulse">
                  thinking...
                </div>
              </div>
            )}

            {error && (
              <p className="text-xs text-red-400 text-center">
                Something went wrong. Try again.
              </p>
            )}

            <div ref={bottomRef} />
          </div>

          {/* Input */}
          <form
            onSubmit={handleSubmit}
            className="border-t border-border px-3 py-2 flex gap-2"
          >
            <input
              value={input}
              onChange={handleInputChange}
              placeholder="Ask anything..."
              disabled={isLoading}
              className="flex-1 bg-transparent text-sm text-white placeholder-gray-500 outline-none"
            />
            <button
              type="submit"
              disabled={isLoading || !input.trim()}
              className="text-indigo-400 hover:text-indigo-300 disabled:opacity-30 text-sm font-medium transition-colors"
            >
              Send
            </button>
          </form>
        </div>
      )}
    </>
  );
}
