"use client";

import { type ReactNode, useEffect, useState } from "react";
import IncidentTimeline from "@/components/incidents/IncidentTimeline";
import { Badge, Button, Empty, Notice, PageHeader, Panel, type Tone } from "@/components/ui";
import { getIncident, listIncidents } from "@/lib/intelligenceApi";
import { formatDuration, shortSha, utcTime } from "@/lib/format";
import { IncidentDetail, IncidentSummary, RootCause } from "@/types";

const confidenceTone: Record<RootCause["confidence"], Tone> = { likely: "bad", possible: "warn", weak: "neutral" };
const signalNames: Record<string, string> = {
  files: "Stack-trace files", timing: "Timing", recovery: "Recovery", type: "Type fit", service: "Service", risk: "Risk",
};

function Field({ label, children }: { label: string; children: ReactNode }) {
  return <section className="py-4 border-t border-line first:border-t-0 first:pt-0">
    <h3 className="text-[12px] font-medium text-muted mb-2">{label}</h3>
    {children}
  </section>;
}

function CauseCard({ cause, rank }: { cause: RootCause; rank: number }) {
  return <div className={`rounded-md border p-3 ${rank === 0 ? "border-line-strong bg-paper" : "border-line"}`}>
    <div className="flex items-center gap-2 flex-wrap">
      <span className="font-mono text-[12px] text-muted">#{rank + 1}</span>
      <span className="text-[13.5px] font-medium text-ink">{cause.title}</span>
      <Badge tone={confidenceTone[cause.confidence]}>{cause.confidence}</Badge>
      <span className="font-mono text-[12px] text-ink-2">{cause.score.toFixed(2)}</span>
    </div>
    <ul className="mt-2 list-disc pl-5 text-[12.5px] text-ink-2 flex flex-col gap-0.5 marker:text-muted">
      {cause.evidence.map((line) => <li key={line}>{line}</li>)}
    </ul>
    {!!cause.commits.length && <p className="mt-2 text-[12px] text-muted">
      Shipped {cause.commits.length} commit{cause.commits.length === 1 ? "" : "s"}:{" "}
      <span className="font-mono text-ink-2">{cause.commits.map((commit) => shortSha(commit.sha)).join(", ")}</span>
    </p>}
    <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-[11.5px] text-muted">
      {Object.entries(cause.signals).map(([key, value]) => <span key={key}>
        {signalNames[key] ?? key} <span className="font-mono text-ink-2">{Math.round((value ?? 0) * 100)}%</span>
      </span>)}
    </div>
  </div>;
}

function Detail({ incident, onAi, busy }: { incident: IncidentDetail; onAi: () => void; busy: boolean }) {
  const top = incident.candidates[0];
  return <Panel
    title={<span>{incident.title}</span>}
    aside={<Button variant="ghost" className="h-7" onClick={onAi} disabled={busy}>{busy ? "Writing…" : "AI summary"}</Button>}
  >
    <div className="flex items-center gap-2 flex-wrap text-[12.5px] text-ink-2">
      <Badge tone={incident.status === "ongoing" ? "bad" : "good"}>{incident.status}</Badge>
      <Badge tone={incident.severity === "critical" ? "bad" : "warn"}>{incident.severity}</Badge>
      <span>{utcTime(incident.start, true)} – {utcTime(incident.end)} UTC · {formatDuration(incident.durationMinutes)}</span>
      <span>· {incident.errorCount} signals, {incident.distinctErrors} distinct</span>
    </div>
    <p className="mt-1 text-[12px] text-muted">Affected: {incident.services.join(", ") || "unknown service"} · seen in {incident.sources.join(", ")}</p>

    <div className="mt-5">
      <Field label={incident.narrativeMode === "groq" ? "Summary (Groq, from the evidence below)" : "Summary"}>
        <p className="text-[13.5px] leading-6 text-ink-2">{incident.narrative}</p>
      </Field>

      <Field label="Likely root cause, ranked">
        {incident.candidates.length
          ? <div className="flex flex-col gap-2">{incident.candidates.map((cause, index) => <CauseCard key={cause.ref + cause.title} cause={cause} rank={index} />)}</div>
          : <p className="text-[13px] text-ink-2">No deploy, migration, config change or commit went live in the 24 hours before this incident.</p>}
        {top?.confidence === "weak" && <div className="mt-2"><Notice tone="warn">Weak evidence: confirm with the timeline before acting.</Notice></div>}
      </Field>

      <Field label="Suggested next steps">
        <ol className="list-decimal pl-5 flex flex-col gap-1 text-[13.5px] text-ink-2 marker:text-muted">
          {incident.nextSteps.map((step) => <li key={step}>{step}</li>)}
        </ol>
        <p className="mt-2 text-[11.5px] text-muted">Suggestions only. AEIP never rolls back, deploys or changes anything.</p>
      </Field>

      <Field label="Timeline across tools (UTC)">
        <IncidentTimeline entries={incident.timeline} start={incident.start} end={incident.end} highlightRef={top?.ref} />
      </Field>
    </div>
  </Panel>;
}

export default function IncidentsPage() {
  const [incidents, setIncidents] = useState<IncidentSummary[] | null>(null);
  const [sources, setSources] = useState<Record<string, number>>({});
  const [error, setError] = useState("");
  const [selected, setSelected] = useState<IncidentDetail | null>(null);
  const [loading, setLoading] = useState("");

  async function open(id: string, useAi = false) {
    setLoading(id);
    setError("");
    try {
      setSelected(await getIncident(id, useAi));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not load the incident.");
    } finally {
      setLoading("");
    }
  }

  useEffect(() => {
    listIncidents().then((data) => {
      setIncidents(data.incidents);
      setSources(data.eventsBySource);
      const wanted = new URLSearchParams(window.location.search).get("id");
      const first = data.incidents.find((item) => item.id === wanted) ?? data.incidents[0];
      if (first) open(first.id);
    }).catch((reason: Error) => setError(reason.message));
  }, []);

  const connected = Object.entries(sources).map(([name, count]) => `${name} ${count}`).join(" · ");
  return <div className="flex flex-col gap-6">
    <PageHeader title="Incidents"
      meta={<>Production errors from every connected tool, grouped into incidents, each traced to the change that most likely caused it.
        {connected && <> Events: <span className="font-mono">{connected}</span>.</>}</>} />
    {error && <Notice tone="bad">{error}</Notice>}
    {incidents && !incidents.length && <Panel>
      <Empty>No incidents. {Object.keys(sources).length ? "No error signals in the connected events." :
        "Send deploy, application, database or alert events to POST /api/events to start correlating."}</Empty>
    </Panel>}
    {incidents && !!incidents.length && <div className="grid grid-cols-1 xl:grid-cols-[minmax(0,0.8fr)_minmax(0,1.4fr)] gap-6 items-start">
      <Panel flush title="Incidents" aside={`${incidents.length} found`}>
        <ul className="divide-y divide-line">
          {incidents.map((item) => {
            const active = selected?.id === item.id;
            return <li key={item.id}>
              <button onClick={() => open(item.id)} disabled={!!loading}
                className={`w-full text-left px-4 py-3 transition-colors ${active ? "bg-accent-soft/60" : "hover:bg-paper"}`}>
                <div className="flex items-center gap-2">
                  <span className={`w-[7px] h-[7px] rounded-full shrink-0 ${item.status === "ongoing" ? "bg-bad" : "bg-good"}`} aria-label={item.status} />
                  <span className="text-[13.5px] font-medium text-ink truncate">{item.title}</span>
                </div>
                <p className="mt-0.5 pl-[15px] text-[12px] text-muted">
                  {utcTime(item.start, true)} UTC · {formatDuration(item.durationMinutes)} · {item.errorCount} signals · {item.services.join(", ")}
                </p>
                {item.rootCause && <p className="mt-1 pl-[15px] text-[12.5px] text-ink-2 truncate">
                  <span className="text-muted">Cause ({item.rootCause.confidence}):</span> {item.rootCause.title}
                </p>}
                {loading === item.id && <p className="mt-1 pl-[15px] text-[12px] text-muted">Loading…</p>}
              </button>
            </li>;
          })}
        </ul>
      </Panel>
      <div>
        {selected ? <Detail incident={selected} busy={loading === selected.id} onAi={() => open(selected.id, true)} />
          : <div className="border border-dashed border-line-strong rounded-md p-6 text-[13px] text-muted">Choose an incident.</div>}
      </div>
    </div>}
  </div>;
}
