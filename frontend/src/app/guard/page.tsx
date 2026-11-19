"use client";

import { type ReactNode, useEffect, useState } from "react";
import Link from "next/link";
import { Badge, Button, Notice, PageHeader, Panel, ScoreBar, type Tone, td, th } from "@/components/ui";
import { assessChange, getOverview } from "@/lib/intelligenceApi";
import { useSession } from "@/lib/useSession";
import { ChangeAssessment, GuardFile } from "@/types";

const levels: Record<ChangeAssessment["level"], { label: string; tone: Tone }> = {
  high: { label: "High risk", tone: "bad" },
  medium: { label: "Medium risk", tone: "warn" },
  low: { label: "Low risk", tone: "good" },
};
const testLabels: Record<NonNullable<GuardFile["tests"]>, { label: string; tone: Tone }> = {
  changed: { label: "updated", tone: "good" },
  "other tests changed": { label: "other tests", tone: "neutral" },
  "not changed": { label: "not updated", tone: "warn" },
  none: { label: "none", tone: "bad" },
};
/** A change that touches the demo incident's file, a migration, a dependency and CI configuration. */
const DEMO_EXAMPLE = ["src/payment_service.py", "src/routes.py", "tests/test_routes.py",
  "db/migrations/0043_refund_status.sql", "requirements.txt", ".github/workflows/deploy.yml"];

function Section({ title, children }: { title: string; children: ReactNode }) {
  return <section className="py-4 border-t border-line first:border-t-0 first:pt-0">
    <h3 className="text-[12px] font-medium text-muted mb-2">{title}</h3>
    {children}
  </section>;
}

function FileTable({ files }: { files: GuardFile[] }) {
  const learned = files.some((file) => file.learned);
  return <div className="overflow-x-auto">
    <table className="w-full border-collapse text-[13px]">
      <thead><tr>
        <th className={th}>File</th>
        <th className={th}>Kind</th>
        <th className={`${th} w-[170px]`}>Risk score</th>
        {learned && <th className={`${th} text-right`} title="Learned chance this file needs a bug fix within 90 days of changing">Learned</th>}
        <th className={th}>Tests</th>
        <th className={th}>Incidents</th>
      </tr></thead>
      <tbody>{files.map((file) => <tr key={file.path} className="hover:bg-paper align-top">
        <td className={`${td} font-mono text-[12.5px] text-ink break-all`} title={file.reasons?.join("\n")}>
          {file.path}
          {file.status !== "modified" && <span className="ml-2 font-sans text-[11.5px] text-muted">{file.status}</span>}
        </td>
        <td className={`${td} text-[12.5px] text-ink-2`}>{file.kind}</td>
        <td className={td}>{file.score !== undefined ? <ScoreBar score={file.score} /> : <span className="text-muted">–</span>}</td>
        {learned && <td className={`${td} text-right font-mono`} title={[...(file.learned?.drivers ?? []), file.learned?.trackRecord].filter(Boolean).join("\n")}>
          {file.learned ? `${Math.round(file.learned.probability * 100)}%` : "–"}
        </td>}
        <td className={td}>{file.tests ? <Badge tone={testLabels[file.tests].tone}>{testLabels[file.tests].label}</Badge> : <span className="text-muted">–</span>}</td>
        <td className={`${td} text-[12.5px]`}>
          {!file.confirmedIncidents && !file.suspectedIn.length && <span className="text-muted">–</span>}
          {!!file.confirmedIncidents && <Badge tone="bad">caused {file.confirmedIncidents}</Badge>}
          {file.suspectedIn.map((incident) => <Link key={incident.id} href={`/incidents?id=${incident.id}`}
            className="block text-accent hover:underline">{incident.title}</Link>)}
        </td>
      </tr>)}</tbody>
    </table>
  </div>;
}

function Report({ result }: { result: ChangeAssessment }) {
  const level = levels[result.level];
  const { change } = result;
  return <Panel title={<span>
    {change.number ? <>Pull request <a href={change.url} target="_blank" rel="noreferrer" className="text-accent hover:underline">#{change.number}</a> · </> : null}
    {change.title}
  </span>}>
    <div className="flex items-center gap-2 flex-wrap text-[12.5px] text-ink-2">
      <Badge tone={level.tone}>{level.label}</Badge>
      <span>{change.files} file{change.files === 1 ? "" : "s"}{change.shown < change.files ? ` (first ${change.shown} shown)` : ""}</span>
      {!!(change.additions || change.deletions) && <span className="font-mono">+{change.additions} −{change.deletions}</span>}
      {change.author && <span>· by {change.author}</span>}
      {change.state && <span>· {change.state}</span>}
    </div>

    <div className="mt-5">
      <Section title="What could break">
        {result.findings.length
          ? <ul className="list-disc pl-5 flex flex-col gap-1 text-[13.5px] text-ink-2 marker:text-muted">
            {result.findings.map((finding) => <li key={finding}>{finding}</li>)}
          </ul>
          : <p className="text-[13.5px] text-ink-2">Nothing in the evidence points at a risk: no risky files, incidents or untested code.</p>}
      </Section>

      <Section title="Before merging">
        {result.checks.length
          ? <ol className="list-decimal pl-5 flex flex-col gap-1 text-[13.5px] text-ink-2 marker:text-muted">
            {result.checks.map((check) => <li key={check}>{check}</li>)}
          </ol>
          : <p className="text-[13.5px] text-ink-2">Normal review is enough.</p>}
      </Section>

      <Section title="Suggested reviewers">
        {result.reviewers.length
          ? <ul className="flex flex-col gap-1 text-[13.5px] text-ink-2">
            {result.reviewers.map((reviewer) => <li key={reviewer.name}>
              <span className="text-ink font-medium">{reviewer.name}</span>
              <span className="text-muted"> · {reviewer.commits} commit{reviewer.commits === 1 ? "" : "s"} to </span>
              <span className="font-mono text-[12.5px]">{reviewer.files.join(", ")}</span>
            </li>)}
          </ul>
          : <p className="text-[13.5px] text-muted">Nobody else changed these files in the last year.</p>}
      </Section>

      <Section title="If it goes wrong: rollback plan">
        <ol className="list-decimal pl-5 flex flex-col gap-1 text-[13.5px] text-ink-2 marker:text-muted">
          {result.rollback.map((step) => <li key={step}>{step}</li>)}
        </ol>
      </Section>

      <Section title="Files">
        <FileTable files={result.files} />
        <p className="mt-2 text-[11.5px] text-muted">
          Scores describe each file with this change included. {result.model.active
            ? <>Learned: {result.model.meaning} Hover a value for its reasons and this repository&apos;s track record.</>
            : <>{result.model.message}.</>}
        </p>
      </Section>
    </div>
    <p className="mt-2 text-[11.5px] text-muted">AEIP only reports: it never comments on, blocks or changes a pull request.</p>
  </Panel>;
}

export default function GuardPage() {
  const { can } = useSession();
  const [repository, setRepository] = useState<{ name: string; demo: boolean } | null>(null);
  const [pullRequest, setPullRequest] = useState("");
  const [files, setFiles] = useState("");
  const [result, setResult] = useState<ChangeAssessment | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    getOverview().then((data) => setRepository({ name: data.repository, demo: data.source === "demo fixture" }))
      .catch((reason: Error) => setError(reason.message));
    // Shareable links: /guard?pr=42 or /guard?files=src/a.py,db/migrations/1.sql open with the check already run.
    const query = new URLSearchParams(window.location.search);
    const pr = query.get("pr");
    const listed = (query.get("files") ?? "").split(",").map((item) => item.trim()).filter(Boolean);
    // eslint-disable-next-line react-hooks/set-state-in-effect -- one-time fill from the URL, then the same check a click runs
    if (pr) { setPullRequest(pr); check({ pullRequest: pr }); }
    else if (listed.length) { setFiles(listed.join("\n")); check({ files: listed }); }
  }, []);

  async function check(input: { pullRequest?: string; files?: string[] }) {
    setBusy(true);
    setError("");
    try {
      setResult(await assessChange(input));
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Could not assess the change.");
    } finally {
      setBusy(false);
    }
  }

  const fileList = files.split(/\r?\n/).map((line) => line.trim()).filter(Boolean);
  const allowed = can("member");
  return <div className="flex flex-col gap-6">
    <PageHeader title="Change guard"
      meta={<>Before a change is merged: what it could break, who should review it, and how to undo it, from this repository&apos;s
        history and incidents{repository ? <> (<span className="font-mono">{repository.name}</span>)</> : null}.</>} />
    {error && <Notice tone="bad">{error}</Notice>}

    <Panel title="Check a change">
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        <form onSubmit={(event) => { event.preventDefault(); check({ pullRequest }); }}>
          <label htmlFor="pr" className="block text-[12px] font-medium text-muted mb-1.5">Pull request number</label>
          <div className="flex gap-2">
            <input id="pr" value={pullRequest} onChange={(event) => setPullRequest(event.target.value)} placeholder="e.g. 42"
              inputMode="numeric" disabled={repository?.demo}
              className="w-40 h-9 px-3 bg-panel border border-line-strong rounded-[5px] font-mono text-[13px] text-ink placeholder:font-sans placeholder:text-muted outline-none focus:border-accent disabled:opacity-60" />
            <Button type="submit" variant="primary" className="h-9" disabled={busy || !pullRequest.trim() || !allowed || repository?.demo}>
              {busy ? "Checking…" : "Check pull request"}
            </Button>
          </div>
          <p className="mt-2 text-[12px] text-muted">
            {repository?.demo ? "The demo repository is not on GitHub: list files instead, or try the example."
              : "Fetches the pull request's changed files from GitHub."}
          </p>
        </form>
        <form onSubmit={(event) => { event.preventDefault(); check({ files: fileList }); }}>
          <label htmlFor="files" className="block text-[12px] font-medium text-muted mb-1.5">Or the changed files, one per line</label>
          <textarea id="files" value={files} onChange={(event) => setFiles(event.target.value)} rows={4} spellCheck={false}
            placeholder={"src/payments/service.py\nmigrations/0043_refunds.sql"}
            className="w-full px-3 py-2 bg-panel border border-line-strong rounded-[5px] font-mono text-[12.5px] text-ink placeholder:text-muted outline-none focus:border-accent" />
          <div className="mt-2 flex gap-2 flex-wrap">
            <Button type="submit" className="h-8" disabled={busy || !fileList.length || !allowed}>Check files</Button>
            {repository?.demo && <Button type="button" variant="ghost" className="h-8" disabled={busy || !allowed}
              onClick={() => { setFiles(DEMO_EXAMPLE.join("\n")); check({ files: DEMO_EXAMPLE }); }}>Try the example change</Button>}
          </div>
        </form>
      </div>
      {!allowed && <p className="mt-3 text-[12px] text-muted">Your role is viewer: checking a change needs member access.</p>}
    </Panel>

    {result && <Report result={result} />}
  </div>;
}
