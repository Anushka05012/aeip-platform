import type { ButtonHTMLAttributes, ReactNode } from "react";

export type Tone = "neutral" | "bad" | "warn" | "good" | "accent";

const toneClass: Record<Tone, string> = {
  neutral: "bg-sunken text-ink-2 border-line",
  bad: "bg-bad-soft text-bad border-[#f3cfc9]",
  warn: "bg-warn-soft text-warn border-[#f0dcb2]",
  good: "bg-good-soft text-good border-[#c3e5d2]",
  accent: "bg-accent-soft text-accent border-[#cbd8f7]",
};

export function levelTone(level?: string): Tone {
  return level === "high" ? "bad" : level === "medium" ? "warn" : level === "low" ? "good" : "neutral";
}

export function PageHeader({ title, meta, actions }: { title: string; meta?: ReactNode; actions?: ReactNode }) {
  return <header className="flex items-end justify-between gap-4 flex-wrap pb-5 border-b border-line">
    <div className="min-w-0">
      <h1 className="text-[22px] font-semibold tracking-[-0.01em] text-ink">{title}</h1>
      {meta && <p className="mt-1 text-[13px] text-muted">{meta}</p>}
    </div>
    {actions && <div className="flex items-center gap-2">{actions}</div>}
  </header>;
}

export function Panel({ title, aside, children, className = "", flush = false }: {
  title?: ReactNode; aside?: ReactNode; children: ReactNode; className?: string; flush?: boolean;
}) {
  return <section className={`bg-panel border border-line rounded-md ${className}`}>
    {(title || aside) && <div className="flex items-center justify-between gap-3 px-4 h-11 border-b border-line">
      <h2 className="text-[13px] font-semibold text-ink">{title}</h2>
      {aside && <div className="text-[12px] text-muted">{aside}</div>}
    </div>}
    <div className={flush ? "" : "p-4"}>{children}</div>
  </section>;
}

export function Badge({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return <span className={`inline-flex items-center h-[22px] px-2 rounded-[4px] border text-[12px] font-medium whitespace-nowrap ${toneClass[tone]}`}>
    {children}
  </span>;
}

export function Button({ variant = "secondary", className = "", ...props }: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: "primary" | "secondary" | "ghost";
}) {
  const styles = {
    primary: "bg-ink text-white border-ink hover:bg-[#33312d]",
    secondary: "bg-panel text-ink border-line-strong hover:bg-sunken",
    ghost: "bg-transparent text-ink-2 border-transparent hover:bg-sunken",
  }[variant];
  return <button {...props}
    className={`inline-flex items-center justify-center gap-1.5 h-8 px-3 rounded-[5px] border text-[13px] font-medium transition-colors disabled:opacity-50 disabled:cursor-not-allowed ${styles} ${className}`} />;
}

export function Notice({ tone = "neutral", children }: { tone?: Tone; children: ReactNode }) {
  return <div className={`rounded-[5px] border px-3 py-2 text-[13px] ${toneClass[tone]}`}>{children}</div>;
}

export function Empty({ children }: { children: ReactNode }) {
  return <p className="text-[13px] text-muted py-6 text-center">{children}</p>;
}

export function ScoreBar({ score }: { score: number }) {
  const color = score >= 70 ? "var(--color-bad)" : score >= 40 ? "var(--color-warn)" : "var(--color-good)";
  return <div className="flex items-center gap-2 min-w-[120px]">
    <span className="w-7 text-right font-mono text-[13px] text-ink">{score}</span>
    <div className="flex-1 h-[6px] rounded-full bg-sunken overflow-hidden" aria-hidden>
      <div className="h-full rounded-full" style={{ width: `${Math.max(score, 2)}%`, background: color }} />
    </div>
  </div>;
}

/** Plain table header cell / cell styles shared by every table in the app. */
export const th = "px-4 h-9 text-left text-[12px] font-medium text-muted border-b border-line whitespace-nowrap";
export const td = "px-4 py-2.5 border-b border-line align-middle";
