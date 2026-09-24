"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { getHealth } from "@/lib/intelligenceApi";
import { useActiveRepository } from "@/lib/useActiveRepository";

type Status = { state: "checking" } | { state: "up"; llm: string } | { state: "down" };

export default function Topbar() {
    const repository = useActiveRepository();
    const [status, setStatus] = useState<Status>({ state: "checking" });

    useEffect(() => {
        getHealth().then((health) => setStatus({ state: "up", llm: health.llm })).catch(() => setStatus({ state: "down" }));
    }, []);

    const dot = status.state === "up" ? "bg-good" : status.state === "down" ? "bg-bad" : "bg-line-strong";
    const label = status.state === "up"
        ? `API online · ${status.llm === "groq" ? "Groq LLM" : "offline mode"}`
        : status.state === "down" ? "API offline" : "Checking API";

    return (
        <div className="h-14 shrink-0 border-b border-line bg-panel px-6 lg:px-10 flex items-center justify-between gap-4">
            <div className="flex items-center gap-2 min-w-0 text-[13.5px]">
                <span className="text-muted">Repository</span>
                <span className="font-mono text-ink truncate">{repository || "acme/payments-api"}</span>
                {!repository && <span className="text-muted">(demo data)</span>}
                <Link href="/repositories" className="ml-1 text-accent hover:underline underline-offset-2">Change</Link>
            </div>
            <div className="flex items-center gap-2 text-[12.5px] text-ink-2 shrink-0" title="Intelligence service on :8001">
                <span className={`w-2 h-2 rounded-full ${dot}`} />
                {label}
            </div>
        </div>
    );
}
