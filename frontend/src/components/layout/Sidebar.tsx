"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { LayoutGrid, GitBranch, ShieldAlert, Terminal, MessageSquare } from "lucide-react";

const navItems = [
    { icon: LayoutGrid, label: "Overview", href: "/" },
    { icon: GitBranch, label: "Repositories", href: "/repositories" },
    { icon: ShieldAlert, label: "Risk Intel", href: "/risk" },
    { icon: Terminal, label: "Failures", href: "/failures" },
    { icon: MessageSquare, label: "Assistant", href: "/assistant" },
];

export default function Sidebar() {
    const pathname = usePathname();

    return (
        <aside className="w-[220px] border-r border-[#1B1F28] flex flex-col shrink-0 min-h-screen">
            <div className="px-5 py-6 border-b border-[#1B1F28]">
                <div className="flex items-center gap-2">
                    <div className="w-6 h-6 rounded bg-[#3FD6B0] flex items-center justify-center">
                        <span className="text-[#0B0D12] font-mono text-xs font-bold">A</span>
                    </div>
                    <span className="font-mono text-[15px] tracking-tight text-[#E7E9EC]">AEIP</span>
                </div>
            </div>
            <nav className="flex-1 py-4">
                {navItems.map((item) => {
                    const Icon = item.icon;
                    const isActive = pathname === item.href;
                    return (
                        <Link
                            key={item.href}
                            href={item.href}
                            className={`w-full flex items-center gap-3 px-5 py-2.5 text-[13.5px] transition-colors ${isActive
                                    ? "text-[#E7E9EC] bg-[#12151C] border-r-2 border-[#3FD6B0]"
                                    : "text-[#767D8A] hover:text-[#B4B9C2]"
                                }`}
                        >
                            <Icon size={16} strokeWidth={1.75} />
                            {item.label}
                        </Link>
                    );
                })}
            </nav>
            <div className="px-5 py-4 border-t border-[#1B1F28] text-[11px] text-[#4A4F5A] font-mono">
                v0.2-sprint2-complete
            </div>
        </aside>
    );
}