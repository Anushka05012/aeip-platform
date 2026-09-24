import { Metric } from "@/types";

/** The four headline numbers as one strip, divided by hairlines rather than separate cards. */
export default function StatStrip({ metrics }: { metrics: Metric[] }) {
    return (
        <div className="border border-line rounded-md overflow-hidden grid grid-cols-2 lg:grid-cols-4 gap-px bg-line">
            {metrics.map((m) => (
                <div key={m.label} className="bg-panel px-5 py-4">
                    <p className="text-[12.5px] text-muted">{m.label}</p>
                    <p className="mt-1.5 flex items-baseline gap-1">
                        <span className="font-mono text-[26px] leading-none font-medium tracking-[-0.02em] text-ink">{m.value}</span>
                        <span className="font-mono text-[13px] text-muted">{m.unit}</span>
                    </p>
                    <p className="mt-2 text-[12px] text-ink-2">{m.delta}</p>
                </div>
            ))}
        </div>
    );
}
