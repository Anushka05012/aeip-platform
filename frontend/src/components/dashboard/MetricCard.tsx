import { TrendingUp, TrendingDown } from "lucide-react";
import { Metric } from "@/types";

export default function MetricCard({ m }: { m: Metric }) {
    return (
        <div className="bg-[#12151C] border border-[#232833] rounded-md p-5 flex flex-col gap-3">
            <span className="text-[13px] text-[#8B93A1]">{m.label}</span>
            <div className="flex items-end gap-2">
                <span className="font-mono text-3xl text-[#E7E9EC] tracking-tight">{m.value}</span>
                <span className="font-mono text-sm text-[#5B6270] mb-1">{m.unit}</span>
            </div>
            <div className={`flex items-center gap-1 text-[12px] font-mono ${m.up ? "text-[#3FD6B0]" : "text-[#F0655A]"}`}>
                {m.up ? <TrendingUp size={13} /> : <TrendingDown size={13} />}
                {m.delta} vs last sprint
            </div>
        </div>
    );
}