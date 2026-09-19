"use client";

import { useState } from "react";
import { Send } from "lucide-react";
import { ChatMessage } from "@/types";

export default function ChatPanel({ initial }: { initial: ChatMessage[] }) {
    const [messages, setMessages] = useState<ChatMessage[]>(initial);
    const [msg, setMsg] = useState("");

    const handleSend = () => {
        if (!msg.trim()) return;
        setMessages([...messages, { role: "user", content: msg }]);
        setMsg("");
        // TODO: replace with real call to Neeraj's Chat API endpoint
    };

    return (
        <div className="bg-[#12151C] border border-[#232833] rounded-md p-5 flex flex-col h-full">
            <span className="text-[13px] text-[#B4B9C2] mb-3">AI assistant</span>
            <div className="flex-1 flex flex-col gap-3 mb-3 overflow-y-auto">
                {messages.map((m, i) =>
                    m.role === "user" ? (
                        <div key={i} className="bg-[#171A21] border border-[#232833] rounded-md rounded-tl-none px-3 py-2 text-[12.5px] text-[#B4B9C2] max-w-[90%]">
                            {m.content}
                        </div>
                    ) : (
                        <div key={i} className="bg-[#0F2B26] border border-[#1F4A40] rounded-md rounded-tr-none px-3 py-2 text-[12.5px] text-[#BFEFE1] max-w-[90%] self-end">
                            {m.content}
                        </div>
                    )
                )}
            </div>
            <div className="flex items-center gap-2 bg-[#0B0D12] border border-[#232833] rounded-md px-3 py-2">
                <input
                    value={msg}
                    onChange={(e) => setMsg(e.target.value)}
                    onKeyDown={(e) => e.key === "Enter" && handleSend()}
                    placeholder="Ask about a failure, repo, or metric..."
                    className="bg-transparent outline-none text-[12.5px] placeholder:text-[#4A4F5A] flex-1 text-[#D8DBE0]"
                />
                <Send size={14} className="text-[#3FD6B0] cursor-pointer" onClick={handleSend} />
            </div>
        </div>
    );
}