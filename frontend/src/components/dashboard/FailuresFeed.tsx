import { Failure } from "@/types";
import { relativeTime, shortSha } from "@/lib/format";
import { Button, td, th } from "@/components/ui";

type Props = { items: Failure[]; onExplain?: (failure: Failure) => void; selectedId?: string; loadingId?: string };

function workflowOf(failure: Failure) {
    return failure.workflow || failure.cause.split(" failed")[0];
}

export default function FailuresFeed({ items, onExplain, selectedId, loadingId }: Props) {
    return (
        <div className="overflow-x-auto">
            <table className="w-full border-collapse text-[13px]">
                <thead>
                    <tr>
                        <th className={th}>Workflow</th>
                        <th className={th}>Commit</th>
                        <th className={th}>Branch</th>
                        <th className={th}>When</th>
                        {onExplain && <th className={th}><span className="sr-only">Action</span></th>}
                    </tr>
                </thead>
                <tbody>
                    {items.map((f, i) => {
                        const selected = selectedId === f.id;
                        const message = f.cause.includes(": ") ? f.cause.slice(f.cause.indexOf(": ") + 2) : "";
                        return (
                            <tr key={f.id ?? i} className={selected ? "bg-accent-soft/60" : "hover:bg-paper"}>
                                <td className={td}>
                                    <div className="flex items-center gap-2">
                                        <span className="w-[7px] h-[7px] rounded-full bg-bad shrink-0" aria-label="failed" />
                                        <span className="text-ink font-medium">{workflowOf(f)}</span>
                                    </div>
                                    {message && <p className="mt-0.5 pl-[15px] text-[12px] text-muted truncate max-w-[320px]" title={message}>{message}</p>}
                                </td>
                                <td className={`${td} font-mono text-[12.5px] text-ink-2`}>{f.commit ? shortSha(f.commit) : "–"}</td>
                                <td className={`${td} font-mono text-[12.5px] text-ink-2 max-w-[160px] truncate`} title={f.branch}>{f.branch}</td>
                                <td className={`${td} text-ink-2 whitespace-nowrap`} title={f.time}>{relativeTime(f.time)}</td>
                                {onExplain && <td className={`${td} text-right`}>
                                    <Button variant={selected ? "primary" : "secondary"} disabled={!!loadingId} onClick={() => onExplain(f)}>
                                        {loadingId === f.id ? "Analysing…" : "Explain"}
                                    </Button>
                                </td>}
                            </tr>
                        );
                    })}
                </tbody>
            </table>
        </div>
    );
}
