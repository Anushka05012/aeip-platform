"use client";

import { useEffect, useRef, useState } from "react";
import { ChatMessage, Evidence } from "@/types";
import { askAssistant } from "@/lib/intelligenceApi";
import { useActiveRepository } from "@/lib/useActiveRepository";
import { useSession } from "@/lib/useSession";
import Markdown from "@/components/Markdown";
import { Button, Notice } from "@/components/ui";

type Message = ChatMessage & { evidence?: Evidence[]; mode?: string };

const SUGGESTIONS = [
  "What does this project do, and where is the main logic?",
  "Which files are riskiest, and what should be tested before deploying?",
  "Why has CI been failing recently?",
];

function Sources({ evidence }: { evidence: Evidence[] }) {
  const seen = new Map<string, number>();
  for (const item of evidence) seen.set(item.path, Math.max(seen.get(item.path) ?? 0, item.score));
  return <ol className="mt-4 pt-3 border-t border-line text-[12.5px] text-muted flex flex-col gap-0.5">
    {[...seen.entries()].map(([path, score], index) => <li key={path} className="flex gap-2">
      <span className="w-4 text-right">{index + 1}.</span>
      <span className="font-mono text-ink-2 break-all">{path}</span>
      <span className="ml-auto font-mono">{score.toFixed(2)}</span>
    </li>)}
  </ol>;
}

export default function ChatPanel({ initial }: { initial: ChatMessage[] }) {
  const { can } = useSession();
  const [messages, setMessages] = useState<Message[]>(initial);
  const [msg, setMsg] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const repository = useActiveRepository();
  const endRef = useRef<HTMLDivElement>(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth", block: "end" }); }, [messages, loading]);

  // Deep link: /assistant?q=... asks the question on load (once, even when dev mode re-runs effects).
  const askedFromLink = useRef(false);
  useEffect(() => {
    const question = new URLSearchParams(window.location.search).get("q");
    if (question && !askedFromLink.current) {
      askedFromLink.current = true;
      queueMicrotask(() => handleSend(question));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSend(text = msg) {
    const question = text.trim();
    if (!question || loading) return;
    setMessages((current) => [...current, { role: "user", content: question }]);
    setMsg("");
    setError("");
    setLoading(true);
    try {
      const response = await askAssistant(question, repository);
      setMessages((current) => [...current, { role: "assistant", content: response.answer, evidence: response.evidence, mode: response.mode }]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to reach the intelligence service.");
    } finally {
      setLoading(false);
    }
  }

  return <div className="flex flex-col gap-5">
    {!messages.length && <div className="bg-panel border border-line rounded-md p-5">
      <p className="text-[13.5px] text-ink-2">Questions are answered from this repository&apos;s code, docs, commit history and CI failures. Each answer lists the excerpts it used.</p>
      <p className="mt-4 mb-2 text-[12px] font-medium text-muted">Try</p>
      <div className="flex flex-col items-start gap-1.5">
        {SUGGESTIONS.map((suggestion) => <button key={suggestion} onClick={() => handleSend(suggestion)}
          className="text-left text-[13.5px] text-accent hover:underline underline-offset-2">{suggestion}</button>)}
      </div>
    </div>}

    {messages.map((message, index) => message.role === "user" ? (
      <div key={index} className="pt-2">
        <p className="text-[12px] font-medium text-muted mb-1">Question</p>
        <p className="text-[15px] font-medium text-ink whitespace-pre-wrap">{message.content}</p>
      </div>
    ) : (
      <article key={index} className="bg-panel border border-line rounded-md p-5">
        <Markdown text={message.content} />
        {!!message.evidence?.length && <Sources evidence={message.evidence} />}
        <p className="mt-2 text-[11.5px] text-muted">
          {message.mode === "groq" ? "Written by Groq from the retrieved excerpts only." : "Extractive answer: no LLM key configured."}
        </p>
      </article>
    ))}

    {loading && <p className="text-[13px] text-muted">Searching {repository || "the repository"}…</p>}
    {error && <Notice tone="bad">{error}</Notice>}
    <div ref={endRef} />

    <form className="sticky bottom-0 bg-paper pt-2 pb-1" onSubmit={(event) => { event.preventDefault(); handleSend(); }}>
      <div className="flex gap-2">
        <input value={msg} onChange={(event) => setMsg(event.target.value)} placeholder="Ask about the code, a failure, or a risky file"
          className="flex-1 min-w-0 h-10 px-3 bg-panel border border-line-strong rounded-[5px] text-[14px] text-ink placeholder:text-muted outline-none focus:border-accent" />
        <Button type="submit" variant="primary" className="h-10 px-4" disabled={loading || !msg.trim() || !can("member")}
          title={can("member") ? undefined : "Your role is viewer: ask an admin for member access to run this."}>Ask</Button>
      </div>
    </form>
  </div>;
}
