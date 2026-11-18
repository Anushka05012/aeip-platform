"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import { useSession } from "@/lib/useSession";
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

function UserMenu() {
    const { session } = useSession();
    if (!session?.user) return null;
    if (!session.enabled) {
        return <span className="text-[12px] text-muted" title="Set AUTH_SECRET, GITHUB_CLIENT_ID and GITHUB_CLIENT_SECRET to require sign-in">
            Login off (local dev)
        </span>;
    }
    const { user } = session;
    return (
        <form action="/api/auth/logout" method="post" className="flex items-center gap-2">
            {user.avatar && <span aria-hidden className="w-[22px] h-[22px] rounded-full bg-cover bg-center bg-sunken" style={{ backgroundImage: `url(${user.avatar})` }} />}
            <span className="text-[12.5px] text-ink">{user.login}</span>
            <span className="text-[11px] uppercase tracking-[0.05em] text-muted">{user.role}</span>
            <button type="submit" className="text-[12.5px] text-accent hover:underline underline-offset-2">Sign out</button>
        </form>
    );
}

type Status = { state: "checking" } | { state: "up"; llm: string } | { state: "down" };

export default function Topbar() {
    const repository = useActiveRepository();
    const pathname = usePathname();
    const [status, setStatus] = useState<Status>({ state: "checking" });

    useEffect(() => {
        if (pathname === "/login") return;
        getHealth().then((health) => setStatus({ state: "up", llm: health.llm })).catch(() => setStatus({ state: "down" }));
    }, [pathname]);
    if (pathname === "/login") return null;

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
                <UserMenu />
            </div>
        </div>
    );
}
