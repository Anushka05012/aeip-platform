import { shortSha, utcTime } from "@/lib/format";
import { TimelineEntry } from "@/types";

/** Label + dot colour per source. The label is always shown, so colour is never the only cue. */
const sources: Record<string, { label: string; dot: string }> = {
    vcs: { label: "Code", dot: "bg-muted" },
    ci: { label: "CI", dot: "bg-ink-2" },
    deploy: { label: "Deploy", dot: "bg-accent" },
    app: { label: "App", dot: "bg-bad" },
    database: { label: "Database", dot: "bg-warn" },
    alert: { label: "Alert", dot: "bg-bad" },
    infra: { label: "Infra", dot: "bg-warn" },
};

type Row = { entry: TimelineEntry; count: number; last: string };

/** Repeats of one error (same fingerprint) collapse into a single row with a count. */
function collapse(entries: TimelineEntry[]): Row[] {
    const rows: Row[] = [];
    const byFingerprint = new Map<string, Row>();
    for (const entry of entries) {
        const key = entry.fingerprint && !entry.kind.startsWith("alert.") ? `${entry.source}|${entry.fingerprint}` : "";
        const existing = key ? byFingerprint.get(key) : undefined;
        if (existing) {
            existing.count += 1;
            existing.last = entry.time;
            continue;
        }
        const row = { entry, count: 1, last: entry.time };
        rows.push(row);
        if (key) byFingerprint.set(key, row);
    }
    return rows;
}

function weight(entry: TimelineEntry) {
    if (entry.severity === "critical" || entry.severity === "error") return "text-ink font-medium";
    if (entry.source === "deploy") return "text-ink";
    return "text-ink-2";
}

export default function IncidentTimeline({ entries, start, end, highlightRef }: {
    entries: TimelineEntry[]; start: string; end: string; highlightRef?: string;
}) {
    const rows = collapse(entries);
    const startMs = new Date(start).getTime();
    const endMs = new Date(end).getTime();
    return (
        <ol className="relative">
            {rows.map(({ entry, count, last }) => {
                const known = sources[entry.source] ?? { label: entry.source, dot: "bg-muted" };
                const recovered = entry.kind === "alert.resolved" || entry.kind === "infra.up";
                const source = recovered ? { ...known, dot: "bg-good" } : known;
                const time = new Date(entry.time).getTime();
                const inside = time >= startMs && time <= endMs;
                const suspect = highlightRef && entry.ref === highlightRef;
                return (
                    <li key={`${entry.ref}-${entry.time}`} className={`grid grid-cols-[52px_14px_minmax(0,1fr)] gap-x-3 py-[7px] ${inside ? "" : "opacity-70"}`}>
                        <span className="font-mono text-[12px] text-muted pt-[1px] text-right">{utcTime(entry.time)}</span>
                        <span className="relative flex justify-center">
                            <span className="absolute top-0 bottom-[-14px] w-px bg-line" aria-hidden />
                            <span className={`relative mt-[5px] w-[9px] h-[9px] rounded-full ring-2 ring-panel ${source.dot} ${suspect ? "outline outline-2 outline-offset-2 outline-accent" : ""}`} aria-hidden />
                        </span>
                        <div className="min-w-0">
                            <p className="text-[13px] leading-5">
                                <span className="text-[11px] uppercase tracking-[0.05em] text-muted mr-2">{source.label}</span>
                                <span className={weight(entry)}>{entry.title}</span>
                                {count > 1 && <span className="ml-2 font-mono text-[12px] text-bad">×{count}</span>}
                                {suspect && <span className="ml-2 text-[11.5px] font-medium text-accent">suspected cause</span>}
                            </p>
                            <p className="text-[11.5px] text-muted">
                                {[entry.service, entry.environment, entry.commit && `commit ${shortSha(entry.commit)}`,
                                count > 1 && `until ${utcTime(last)}`, entry.files.length ? entry.files.slice(0, 2).join(", ") : ""]
                                    .filter(Boolean).join(" · ")}
                            </p>
                        </div>
                    </li>
                );
            })}
        </ol>
    );
}
