import { RiskItem } from "@/types";

function RiskBar({ score }: { score: number }) {
    const color = score > 80 ? "#F0655A" : score > 55 ? "#F0A93F" : "#3FD6B0";
    return (
        <div className="w-full h-1.5 bg-[#1D212B] rounded-full overflow-hidden">
            <div className="h-full rounded-full" style={{ width: `${score}%`, background: color }} />
        </div>
    );
}

export default function RiskList({ items }: { items: RiskItem[] }) {
    return (
        <div className="bg-[#12151C] border border-[#232833] rounded-md p-5 flex flex-col">
            <span className="text-[13px] text-[#B4B9C2] mb-4">Risk intelligence</span>
            <div className="flex flex-col gap-4">
                {items.map((r) => (
                    <div key={r.file} className="flex flex-col gap-1.5">
                        <div className="flex items-center justify-between">
                            <span className="font-mono text-[11.5px] text-[#B4B9C2] truncate max-w-[160px]">{r.file}</span>
                            <span className="font-mono text-[11.5px] text-[#8B93A1]">{r.score}</span>
                        </div>
                        <RiskBar score={r.score} />
                        <span className="text-[11px] text-[#5B6270]">{r.reason}</span>
                    </div>
                ))}
            </div>
        </div>
    );
}