import { AlertTriangle, Clock } from "lucide-react";
import { Failure, Severity } from "@/types";

const sevColor: Record<Severity, string> = {
    high: "#F0655A",
    medium: "#F0A93F",
    low: "#5B96F0",
};

export default function FailuresFeed({ items }: { items: Failure[] }) {
    return (
        <div className="bg-[#12151C] border border-[#232833] rounded-md p-5">
            <span className="text-[13px] text-[#B4B9C2] mb-4 block">Recent CI/CD failures</span>
            <div className="flex flex-col divide-y divide-[#1D212B]">
                {items.map((f, i) => (
                    <div key={i} className="flex items-center gap-3 py-3">
                        <AlertTriangle size={15} style={{ color: sevColor[f.severity] }} />
                        <div className="flex-1 min-w-0">
                            <div className="text-[13px] text-[#D8DBE0] truncate">{f.cause}</div>
                            <div className="font-mono text-[11px] text-[#5B6270] mt-0.5">{f.repo} · {f.branch}</div>
                        </div>
                        <div className="flex items-center gap-1 text-[11px] text-[#5B6270] shrink-0">
                            <Clock size={11} /> {f.time}
                        </div>
                    </div>
                ))}
            </div>
        </div>
    );
}