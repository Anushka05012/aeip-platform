import { RiskItem } from "@/types";
import { Badge, levelTone, ScoreBar, td, th } from "@/components/ui";

function levelOf(item: RiskItem) {
    return item.level ?? (item.score >= 70 ? "high" : item.score >= 40 ? "medium" : "low");
}

/** Full risk table: every signal that feeds the score is visible, not just the score. */
export function RiskTable({ items }: { items: RiskItem[] }) {
    return (
        <div className="overflow-x-auto">
            <table className="w-full border-collapse text-[13px]">
                <thead>
                    <tr>
                        <th className={th}>File</th>
                        <th className={`${th} w-[190px]`}>Risk score</th>
                        <th className={th}>Level</th>
                        <th className={`${th} text-right`}>Changes</th>
                        <th className={`${th} text-right`}>Lines churned</th>
                        <th className={`${th} text-right`}>Complexity Δ</th>
                    </tr>
                </thead>
                <tbody>
                    {items.map((item) => (
                        <tr key={item.file} className="hover:bg-paper">
                            <td className={`${td} font-mono text-[12.5px] text-ink break-all`}>{item.file}</td>
                            <td className={td}><ScoreBar score={item.score} /></td>
                            <td className={td}><Badge tone={levelTone(levelOf(item))}>{levelOf(item)}</Badge></td>
                            <td className={`${td} text-right font-mono`}>{item.changes ?? "–"}</td>
                            <td className={`${td} text-right font-mono`}>{item.churn?.toLocaleString("en-IN") ?? "–"}</td>
                            <td className={`${td} text-right font-mono`}>{item.complexity === undefined ? "–" : item.complexity > 0 ? `+${item.complexity}` : item.complexity}</td>
                        </tr>
                    ))}
                </tbody>
            </table>
        </div>
    );
}

/** Compact list for the overview page. */
export default function RiskList({ items }: { items: RiskItem[] }) {
    return (
        <ul className="divide-y divide-line">
            {items.map((item) => (
                <li key={item.file} className="px-4 py-2.5 flex items-center gap-3">
                    <span className="flex-1 min-w-0 font-mono text-[12.5px] text-ink truncate" title={item.file}>{item.file}</span>
                    <div className="w-[150px] shrink-0"><ScoreBar score={item.score} /></div>
                </li>
            ))}
        </ul>
    );
}
