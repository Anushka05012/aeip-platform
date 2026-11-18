"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const sections = [
    {
        heading: "Workspace",
        items: [
            { label: "Overview", href: "/" },
            { label: "Repositories", href: "/repositories" },
        ],
    },
    {
        heading: "Investigate",
        items: [
            { label: "Incidents", href: "/incidents" },
            { label: "Change risk", href: "/risk" },
            { label: "CI failures", href: "/failures" },
            { label: "Ask the codebase", href: "/assistant" },
        ],
    },
];

export default function Sidebar() {
    const pathname = usePathname();
    if (pathname === "/login") return null;

    return (
        <aside className="w-[212px] shrink-0 min-h-screen border-r border-line bg-sunken/60 flex flex-col">
            <Link href="/" className="h-14 px-5 flex items-center gap-2.5 border-b border-line">
                <svg width="18" height="18" viewBox="0 0 18 18" aria-hidden>
                    <rect x="1" y="1" width="16" height="16" rx="3" fill="none" stroke="currentColor" strokeWidth="1.6" />
                    <path d="M5 12.5 8 5.5l3 7M6.2 10h3.6M12.5 5.5v7" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
                </svg>
                <span className="text-[15px] font-semibold tracking-[-0.01em]">AEIP</span>
            </Link>
            <nav className="flex-1 px-3 py-5 flex flex-col gap-6">
                {sections.map((section) => (
                    <div key={section.heading}>
                        <p className="px-2 mb-1.5 text-[11px] font-medium uppercase tracking-[0.06em] text-muted">{section.heading}</p>
                        {section.items.map((item) => {
                            const active = pathname === item.href;
                            return (
                                <Link key={item.href} href={item.href}
                                    className={`block px-2 py-[7px] rounded-[5px] text-[13.5px] transition-colors ${active
                                        ? "bg-panel text-ink font-medium shadow-[inset_0_0_0_1px_var(--color-line)]"
                                        : "text-ink-2 hover:bg-panel/70 hover:text-ink"}`}>
                                    {item.label}
                                </Link>
                            );
                        })}
                    </div>
                ))}
            </nav>
            <div className="px-5 py-4 border-t border-line text-[11.5px] leading-5 text-muted">
                VIT Pune · CSA44<br />AI Engineering Intelligence Platform
            </div>
        </aside>
    );
}
