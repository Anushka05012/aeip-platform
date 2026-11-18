"use client";

import { type ReactNode, useEffect, useState } from "react";
import FailuresFeed from "@/components/dashboard/FailuresFeed";
import Markdown from "@/components/Markdown";
import { Badge, Button, Empty, Notice, PageHeader, Panel, type Tone } from "@/components/ui";
import { explainFailure, getOverview } from "@/lib/intelligenceApi";
import { shortSha } from "@/lib/format";
import { Failure, FailureExplanation, FlakyWorkflow } from "@/types";

const verdicts: Record<FailureExplanation["verdict"], { label: string; tone: Tone }> = {
  related: { label: "Caused by the code change", tone: "bad" },
  unrelated: { label: "Not caused by the code change", tone: "good" },
  uncertain: { label: "Inconclusive", tone: "warn" },
};

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <section className="py-4 border-t border-line first:border-t-0 first:pt-0">
    <h3 className="text-[12px] font-medium text-muted mb-2">{label}</h3>
    {children}
  </section>;
}

function FlakyPanel({ items }: { items: FlakyWorkflow[] }) {
  return <Panel title="Flaky workflows" aside={`${items.length} found`}>
    <p className="text-[12.5px] text-muted mb-3">
      A workflow is flaky when it gives different results for the same code: it failed and passed on one commit,
      or passed only on a re-run. Suspected means its results keep alternating, but no run proves it.
    </p>
    <ul className="flex flex-col gap-3">
      {items.map((item) => <li key={item.workflow} className="border-t border-line pt-3 first:border-t-0 first:pt-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-[13.5px] text-ink font-medium">{item.workflow}</span>
          <Badge tone={item.level === "flaky" ? "warn" : "neutral"}>{item.level}</Badge>
          <span className="text-[12px] text-muted">
            {item.failures} of {item.runs} runs failed · results flipped {item.flips} time{item.flips === 1 ? "" : "s"}
          </span>
        </div>
        {!!item.events.length && <ul className="mt-1.5 list-disc pl-5 text-[12.5px] text-ink-2 marker:text-muted">
          {item.events.slice(0, 4).map((event) => <li key={event.kind + event.detail}>
            <span className="text-muted">{event.kind}:</span> {event.detail}
          </li>)}
        </ul>}
      </li>)}
    </ul>
  </Panel>;
}

function Report({ result, onRefresh, busy }: { result: FailureExplanation; onRefresh: () => void; busy: boolean }) {
  const verdict = verdicts[result.verdict];
  return <Panel
    title={<span>{result.workflow} <span className="font-normal text-muted">· run {result.run_id}</span></span>}
    aside={<Button variant="ghost" className="h-7" onClick={onRefresh} disabled={busy}>{busy ? "Re-analysing…" : "Re-analyse"}</Button>}
  >
    <div className="flex items-center gap-2 flex-wrap">
      <Badge tone={verdict.tone}>{verdict.label}</Badge>
      <Badge>{result.category}</Badge>
      <span className="text-[12.5px] text-ink-2">Confidence <span className="font-mono">{Math.round(result.confidence * 100)}%</span></span>
    </div>
    <p className="mt-2 font-mono text-[12px] text-muted">
      {shortSha(result.commit)}{result.commit_message && <> · <span className="font-sans">{result.commit_message}</span></>}
    </p>
    {result.pull_request && <p className="mt-1 text-[12.5px] text-ink-2">
      Pull request <span className="font-mono">#{result.pull_request.number}</span> · {result.pull_request.title}{" "}
      <span className="text-muted">({result.pull_request.state}, into {result.pull_request.base})</span>
    </p>}
    {result.needs_review && <div className="mt-3"><Notice tone="warn">Low confidence: a person should confirm this before anyone acts on it.</Notice></div>}

    <div className="mt-5">
      <Field label="Explanation"><Markdown text={result.explanation} /></Field>

      <Field label="Suggested next steps">
        <ol className="list-decimal pl-5 flex flex-col gap-1 text-[13.5px] text-ink-2 marker:text-muted">
          {result.next_steps.map((step) => <li key={step}>{step}</li>)}
        </ol>
        <p className="mt-2 text-[11.5px] text-muted">Suggestions only. AEIP never changes code or re-runs jobs.</p>
      </Field>

      <Field label="Why (rule-based signals)">
        <ul className="list-disc pl-5 flex flex-col gap-1 text-[13px] text-ink-2 marker:text-muted">
          {result.signals.map((signal) => <li key={signal}>{signal}</li>)}
        </ul>
      </Field>

      {!!result.changed_files.length && <Field label="Files changed by this commit">
        <ul className="flex flex-col gap-1 text-[12.5px]">
          {result.changed_files.map((file) => <li key={file.path} className="flex items-center gap-2 flex-wrap">
            <span className={`font-mono break-all ${file.mentionedInLog ? "text-bad" : "text-ink-2"}`}>{file.path}</span>
            {file.mentionedInLog && <Badge tone="bad">in error output</Badge>}
            {file.risk !== null && <span className="text-muted">risk {file.risk}</span>}
          </li>)}
        </ul>
      </Field>}

      {!!result.error_lines.length && <Field label={`Error output (${result.log_source}, secrets redacted)`}>
        <pre className="font-mono text-[11.5px] leading-[1.6] bg-console text-console-fg rounded-[5px] p-3 overflow-x-auto max-h-72">{result.error_lines.join("\n")}</pre>
      </Field>}

      {!!result.evidence.length && <Field label="Related code">
        <p className="font-mono text-[12.5px] text-ink-2">{[...new Set(result.evidence.map((item) => item.path))].join("  ·  ")}</p>
      </Field>}
    </div>

    <p className="mt-2 text-[11.5px] text-muted">
      {result.mode === "groq" ? "Rules and Groq LLM agreed or were reconciled." : "Rule-based analysis only."}
      {result.cached && " Loaded from cache."}
      {result.notes.map((note) => <span key={note}> {note}</span>)}
    </p>
  </Panel>;
}

export default function FailuresPage() {
  const [failures, setFailures] = useState<Failure[] | null>(null);
  const [flaky, setFlaky] = useState<FlakyWorkflow[]>([]);
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<Failure | null>(null);
  const [result, setResult] = useState<FailureExplanation | null>(null);
  const [loadingId, setLoadingId] = useState("");
  const [explainError, setExplainError] = useState("");

  useEffect(() => {
    getOverview().then((data) => {
      setFailures(data.failures);
      setFlaky(data.flaky ?? []);
      // Deep link: /failures?run=<id> opens that run's explanation directly.
      const run = new URLSearchParams(window.location.search).get("run");
      const target = data.failures.find((item) => item.id === run);
      if (target) explain(target);
    }).catch((reason: Error) => setError(reason.message));
  }, []);

  async function explain(failure: Failure, refresh = false) {
    setSelected(failure);
    setLoadingId(failure.id);
    setExplainError("");
    if (!refresh) setResult(null);
    try {
      setResult(await explainFailure(failure.id, undefined, refresh));
    } catch (reason) {
      setExplainError(reason instanceof Error ? reason.message : "Analysis failed.");
    } finally {
      setLoadingId("");
    }
  }

  return <div className="flex flex-col gap-6">
    <PageHeader title="CI failures" meta="Was a failed run caused by its triggering commit? Explain checks the logs, changed files, risk scores and related code." />
    {error && <Notice tone="bad">{error}</Notice>}
    {!!flaky.length && <FlakyPanel items={flaky} />}
    {failures && !failures.length && <Panel><Empty>No failed CI runs for this repository.</Empty></Panel>}
    {failures && !!failures.length && <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.05fr)] gap-6 items-start">
      <Panel flush title="Failed runs" aside={`${failures.length} shown`}>
        <FailuresFeed items={failures} onExplain={(failure) => explain(failure)} selectedId={selected?.id} loadingId={loadingId} />
      </Panel>
      <div className="xl:sticky xl:top-4">
        {explainError && <Notice tone="bad">{explainError}</Notice>}
        {loadingId && !result && <Panel title="Analysing">
          <ol className="text-[13px] text-ink-2 flex flex-col gap-1.5 list-decimal pl-5 marker:text-muted">
            <li>Fetching failed jobs and logs</li>
            <li>Matching errors against the commit&apos;s changed files</li>
            <li>Retrieving related code</li>
            <li>Asking the LLM for a verdict</li>
          </ol>
        </Panel>}
        {result && selected && <Report result={result} busy={!!loadingId} onRefresh={() => explain(selected, true)} />}
        {!result && !loadingId && !explainError && <div className="border border-dashed border-line-strong rounded-md p-6 text-[13px] text-muted">
          Choose a failed run and select <span className="text-ink font-medium">Explain</span>.
        </div>}
      </div>
    </div>}
  </div>;
}
