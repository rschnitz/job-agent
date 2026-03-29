"use client";

import { useRef, useState } from "react";
import type { Message } from "@/lib/supabase";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Send, Loader2, Sparkles } from "lucide-react";
import { cn } from "@/lib/utils";

const STARTER_PROMPTS = [
  "Review my resume and suggest improvements",
  "Help me write a cold outreach message to a hiring manager",
  "What questions should I prep for an EM interview?",
  "Compare my background to a typical Director of Engineering role",
];

export default function GeneralChat() {
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState("");
  const [streaming, setStreaming] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);

  async function sendMessage(override?: string) {
    const text = (override ?? input).trim();
    if (!text || streaming) return;
    const userMsg: Message = { role: "user", content: text };
    const newMessages = [...messages, userMsg];
    setMessages(newMessages);
    setInput("");
    setStreaming(true);
    setMessages([...newMessages, { role: "assistant", content: "" }]);

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ messages: newMessages }),
      });

      if (!res.ok) {
        setMessages([...newMessages, { role: "assistant", content: "Something went wrong. Please try again." }]);
        return;
      }

      if (!res.body) return;
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let full = "";

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        full += decoder.decode(value);
        setMessages([...newMessages, { role: "assistant", content: full }]);
        bottomRef.current?.scrollIntoView({ behavior: "smooth" });
      }
    } finally {
      setStreaming(false);
    }
  }

  return (
    <div className="max-w-2xl mx-auto flex flex-col h-[calc(100vh-96px)]">
      {/* Header */}
      <div className="mb-4">
        <div className="flex items-center gap-2 mb-0.5">
          <Sparkles className="h-4 w-4 text-primary" />
          <h1 className="text-lg font-semibold">Career Assistant</h1>
        </div>
        <p className="text-sm text-muted-foreground">Ask for job advice, resume feedback, or interview prep</p>
      </div>

      {/* Chat area */}
      <div className="flex-1 flex flex-col rounded-xl border border-border bg-card overflow-hidden">
        <div className="flex-1 overflow-y-auto p-4 space-y-3">
          {messages.length === 0 && (
            <div className="flex flex-col items-center justify-center h-full gap-4 pb-4">
              <div className="h-10 w-10 rounded-full bg-primary/10 flex items-center justify-center">
                <Sparkles className="h-5 w-5 text-primary" />
              </div>
              <div className="text-center">
                <p className="text-sm font-medium text-foreground mb-1">How can I help?</p>
                <p className="text-xs text-muted-foreground">Try one of these to get started</p>
              </div>
              <div className="w-full max-w-sm space-y-1.5">
                {STARTER_PROMPTS.map((prompt) => (
                  <button
                    key={prompt}
                    onClick={() => sendMessage(prompt)}
                    className="w-full text-left text-xs text-muted-foreground border border-border rounded-lg px-3 py-2.5 hover:border-primary/30 hover:text-foreground hover:bg-accent transition-all cursor-pointer"
                  >
                    {prompt}
                  </button>
                ))}
              </div>
            </div>
          )}
          {messages.map((m, i) => (
            <div key={i} className={cn("flex gap-2", m.role === "user" ? "justify-end" : "justify-start")}>
              {m.role === "assistant" && (
                <div className="h-6 w-6 rounded-full bg-primary/10 flex items-center justify-center shrink-0 mt-0.5">
                  <Sparkles className="h-3 w-3 text-primary" />
                </div>
              )}
              <div
                className={cn(
                  "text-sm px-3.5 py-2.5 rounded-2xl max-w-[80%] whitespace-pre-wrap leading-relaxed",
                  m.role === "user"
                    ? "bg-primary text-white rounded-tr-sm"
                    : "bg-accent text-foreground rounded-tl-sm"
                )}
              >
                {m.content || (streaming && i === messages.length - 1 ? (
                  <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
                ) : null)}
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        {/* Input */}
        <div className="p-3 border-t border-border flex gap-2 bg-background/50">
          <Textarea
            className="flex-1 min-h-0 resize-none text-sm"
            rows={2}
            placeholder="Ask anything about your job search..."
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" && !e.shiftKey) {
                e.preventDefault();
                sendMessage();
              }
            }}
          />
          <Button
            size="icon"
            className="self-end shrink-0"
            onClick={() => sendMessage()}
            disabled={streaming || !input.trim()}
          >
            {streaming ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          </Button>
        </div>
      </div>
    </div>
  );
}
