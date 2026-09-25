"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Moon, Sun } from "lucide-react";
import { getHealth } from "@/lib/intelligenceApi";
import { setTheme, useTheme } from "@/lib/theme";
import { useActiveRepository } from "@/lib/useActiveRepository";

function ThemeToggle() {
    const theme = useTheme();
    const next = theme === "dark" ? "light" : "dark";
    return (
        <button onClick={() => setTheme(next)} aria-label={`Switch to ${next} mode`} title={`Switch to ${next} mode`}
            className="inline-flex items-center gap-1.5 h-8 px-2.5 rounded-[5px] border border-line text-[12.5px] text-ink-2 hover:bg-sunken hover:text-ink transition-colors">
            {theme === "dark" ? <Sun size={14} strokeWidth={1.75} /> : <Moon size={14} strokeWidth={1.75} />}
            {theme === "dark" ? "Light" : "Dark"}
        </button>
    );
}

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
            <div className="flex items-center gap-4 shrink-0">
                <div className="flex items-center gap-2 text-[12.5px] text-ink-2" title="Intelligence service on :8001">
                    <span className={`w-2 h-2 rounded-full ${dot}`} />
                    {label}
                </div>
                <ThemeToggle />
            </div>
        </div>
    );
}
