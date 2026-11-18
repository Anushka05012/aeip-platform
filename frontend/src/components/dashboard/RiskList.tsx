import { RiskBreakdown, RiskItem } from "@/types";
import { Badge, levelTone, ScoreBar, td, th } from "@/components/ui";

function levelOf(item: RiskItem) {
    return item.level ?? (item.score >= 70 ? "high" : item.score >= 40 ? "medium" : "low");
}

const signalNames: Record<keyof RiskBreakdown, string> = {
    frequency: "Change frequency", churn: "Lines churned", complexity: "Complexity growth",
    testGap: "Test gap", blastRadius: "Blast radius", dependencies: "Dependency update",
};

function breakdownText(item: RiskItem) {
    if (!item.breakdown) return undefined;
    return (Object.keys(signalNames) as (keyof RiskBreakdown)[])
        .map((key) => `${signalNames[key]}: ${item.breakdown![key]}`).join("\n");
}

function testsCell(item: RiskItem) {
    if (item.hasTests === undefined || !item.breakdown) return <span className="text-muted">–</span>;
    if (item.breakdown.testGap === 0 && !item.hasTests) return <span className="text-muted">n/a</span>;
    if (!item.hasTests) return <Badge tone="bad">none</Badge>;
    return <span className="font-mono">{Math.round((item.testTouchRatio ?? 0) * 100)}%<span className="text-muted font-sans"> of changes</span></span>;
}

/** Full risk table: every signal that feeds the score is visible, not just the score. */
export function RiskTable({ items }: { items: RiskItem[] }) {
    const learned = items.some((item) => item.learned);
    return (
        <div className="overflow-x-auto">
            <table className="w-full border-collapse text-[13px]">
                <thead>
                    <tr>
                        <th className={th}>File</th>
                        <th className={`${th} w-[190px]`}>Risk score</th>
                        {learned && <th className={`${th} text-right`} title="Chance this file breaks soon, from what broke this repository before">Learned</th>}
                        <th className={th}>Level</th>
                        <th className={`${th} text-right`}>Changes</th>
                        <th className={`${th} text-right`}>Lines churned</th>
                        <th className={`${th} text-right`}>Complexity Δ</th>
                        <th className={th} title="Is there a test file for this module, and how often did changes also update tests?">Tests</th>
                        <th className={`${th} text-right`} title="Other files that import this one">Used by</th>
                        <th className={th} title="Changed in the same commit as a dependency manifest or lockfile">Deps</th>
                    </tr>
                </thead>
                <tbody>
                    {items.map((item) => (
                        <tr key={item.file} className="hover:bg-paper">
                            <td className={`${td} font-mono text-[12.5px] text-ink break-all`}>{item.file}</td>
                            <td className={td} title={breakdownText(item)}><ScoreBar score={item.score} /></td>
                            {learned && <td className={`${td} text-right font-mono`}
                                title={[...(item.learned?.drivers ?? []), item.learned?.trackRecord].filter(Boolean).join("\n")}>
                                {item.learned ? `${Math.round(item.learned.probability * 100)}%` : "–"}
                            </td>}
                            <td className={td}><Badge tone={levelTone(levelOf(item))}>{levelOf(item)}</Badge></td>
                            <td className={`${td} text-right font-mono`}>{item.changes ?? "–"}</td>
                            <td className={`${td} text-right font-mono`}>{item.churn?.toLocaleString("en-IN") ?? "–"}</td>
                            <td className={`${td} text-right font-mono`}>{item.complexity === undefined ? "–" : item.complexity > 0 ? `+${item.complexity}` : item.complexity}</td>
                            <td className={`${td} whitespace-nowrap text-[12.5px]`}>{testsCell(item)}</td>
                            <td className={`${td} text-right font-mono`}>{item.dependents ?? "–"}</td>
                            <td className={td}>{item.dependencyChanges ? <Badge tone="warn">updated</Badge> : <span className="text-muted">–</span>}</td>
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
