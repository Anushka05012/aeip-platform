"use client";

import { useState } from "react";
import { Send } from "lucide-react";
import { ChatMessage } from "@/types";
import { askAssistant } from "@/lib/intelligenceApi";

export default function ChatPanel({ initial }: { initial: ChatMessage[] }) {
  const [messages, setMessages] = useState<ChatMessage[]>(initial);
  const [msg, setMsg] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const handleSend = async () => {
    const question = msg.trim();
    if (!question || loading) return;
    setMessages((current) => [...current, { role: "user", content: question }]);
    setMsg("");
    setError("");
    setLoading(true);
    try {
      const response = await askAssistant(question);
      const sources = response.evidence.map((item) => item.path).join(", ");
      setMessages((current) => [...current, { role: "assistant", content: `${response.answer}\n\nSources: ${sources}` }]);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Unable to reach the intelligence service.");
    } finally {
      setLoading(false);
    }
  };

  return <div className="bg-[#12151C] border border-[#232833] rounded-md p-5 flex flex-col h-full">
    <span className="text-[13px] text-[#B4B9C2] mb-3">AI assistant · repository-aware RAG</span>
    <div className="flex-1 flex flex-col gap-3 mb-3 overflow-y-auto">
      {!messages.length && <p className="text-[12.5px] text-[#5B6270]">Ask about the indexed repository, a risky file, or deployment testing.</p>}
      {messages.map((message, index) => message.role === "user" ? (
        <div key={index} className="bg-[#171A21] border border-[#232833] rounded-md rounded-tl-none px-3 py-2 text-[12.5px] text-[#B4B9C2] max-w-[90%] whitespace-pre-wrap">{message.content}</div>
      ) : (
        <div key={index} className="bg-[#0F2B26] border border-[#1F4A40] rounded-md rounded-tr-none px-3 py-2 text-[12.5px] text-[#BFEFE1] max-w-[90%] self-end whitespace-pre-wrap">{message.content}</div>
      ))}
      {loading && <div className="text-[12px] text-[#8B93A1] self-end">Retrieving repository evidence...</div>}
    </div>
    {error && <p className="text-[12px] text-[#F0655A] mb-2">{error}</p>}
    <div className="flex items-center gap-2 bg-[#0B0D12] border border-[#232833] rounded-md px-3 py-2">
      <input value={msg} onChange={(event) => setMsg(event.target.value)} onKeyDown={(event) => event.key === "Enter" && handleSend()} placeholder="Ask about a failure, repo, or metric..." className="bg-transparent outline-none text-[12.5px] placeholder:text-[#4A4F5A] flex-1 text-[#D8DBE0]" />
      <Send size={14} className={`text-[#3FD6B0] ${loading ? "opacity-50" : "cursor-pointer"}`} onClick={handleSend} />
    </div>
  </div>;
}
