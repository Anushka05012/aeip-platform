"use client";

import { GitBranch, ChevronDown, Search } from "lucide-react";

export default function Topbar() {
    return (
        <div className="h-16 border-b border-[#1B1F28] flex items-center justify-between px-8 shrink-0">
            <div className="flex items-center gap-2 text-[14px] text-[#B4B9C2]">
                <GitBranch size={15} className="text-[#5B6270]" />
                <span>AEIP</span>
                <ChevronDown size={14} className="text-[#5B6270]" />
            </div>
            <div className="flex items-center gap-2 bg-[#12151C] border border-[#232833] rounded-md px-3 py-1.5 w-64">
                <Search size={14} className="text-[#5B6270]" />
                <input
                    placeholder="Search commits, PRs, logs..."
                    className="bg-transparent outline-none text-[13px] placeholder:text-[#4A4F5A] w-full text-[#D8DBE0]"
                />
            </div>
        </div>
    );
}