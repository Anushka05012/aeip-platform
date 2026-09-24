"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { analyzeRepository, listRepositories, setActiveRepository } from "@/lib/intelligenceApi";
import { useActiveRepository } from "@/lib/useActiveRepository";
import { formatMs, relativeTime } from "@/lib/format";
import { Badge, Button, Notice, PageHeader, Panel, td, th } from "@/components/ui";
import { RepositorySummary } from "@/types";

const PIPELINE = ["Connect to GitHub", "Commits and churn", "CI runs", "Source and chunking", "Embeddings", "Risk scoring", "DORA metrics"];

function PipelineLog({ summary }: { summary: RepositorySummary }) {
  const total = summary.stages.reduce((sum, stage) => sum + stage.ms, 0);
  return <div className="bg-ink text-[#e8e6e1] rounded-[5px] p-4 font-mono text-[12px] leading-[1.8] overflow-x-auto">
    <p className="text-[#a8a49a]">$ aeip analyze {summary.repository}</p>
    {summary.stages.map((stage) => <p key={stage.stage} className="whitespace-nowrap">
      <span className="text-[#7fd1a4]">✓</span> <span className="inline-block w-[210px]">{stage.stage}</span>
      <span className="inline-block w-[70px] text-right text-[#a8a49a]">{formatMs(stage.ms)}</span>
      <span className="ml-4">{stage.detail}</span>
    </p>)}
    <p className="text-[#a8a49a]">done in {formatMs(total)}</p>
  </div>;
}

export default function RepositoriesPage() {
  const router = useRouter();
  const [input, setInput] = useState("");
  const [repositories, setRepositories] = useState<RepositorySummary[]>([]);
  const active = useActiveRepository();
  const [running, setRunning] = useState("");
  const [step, setStep] = useState(0);
  const [latest, setLatest] = useState<RepositorySummary | null>(null);
  const [error, setError] = useState("");

  const refresh = () => listRepositories().then((data) => setRepositories(data.repositories)).catch((reason: Error) => setError(reason.message));
  useEffect(() => { refresh(); }, []);

  // The backend call is a single request, so the step list is paced client-side.
  useEffect(() => {
    if (!running) return;
    const timer = setInterval(() => setStep((current) => Math.min(current + 1, PIPELINE.length - 1)), 2500);
    return () => clearInterval(timer);
  }, [running]);

  const open = (repository: string, path = "/") => {
    setActiveRepository(repository);
    router.push(path);
  };

  const analyze = async (target: string, reanalyze = false) => {
    if (!target.trim() || running) return;
    setStep(0);
    setRunning(target.trim());
    setError("");
    setLatest(null);
    try {
      const summary = await analyzeRepository(target.trim(), reanalyze);
      setLatest(summary);
      setActiveRepository(summary.repository);
      await refresh();
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Analysis failed.");
    } finally {
      setRunning("");
    }
  };

  const isActive = (repo: RepositorySummary) => repo.repository === active || (!active && repo.source === "demo fixture");

  return <div className="flex flex-col gap-6">
    <PageHeader title="Repositories" meta="Analysing a repository pulls its commits, CI runs and source from GitHub, then indexes, scores and summarises it." />

    <Panel title="Analyse a GitHub repository">
      <form className="flex gap-2 flex-wrap" onSubmit={(event) => { event.preventDefault(); analyze(input); }}>
        <input value={input} onChange={(event) => setInput(event.target.value)} placeholder="owner/repo or https://github.com/owner/repo" spellCheck={false}
          className="flex-1 min-w-60 h-9 px-3 bg-panel border border-line-strong rounded-[5px] font-mono text-[13px] text-ink placeholder:font-sans placeholder:text-muted outline-none focus:border-accent" />
        <Button type="submit" variant="primary" className="h-9" disabled={!!running || !input.trim()}>
          {running ? "Analysing…" : "Analyse"}
        </Button>
      </form>
      <p className="mt-2 text-[12px] text-muted">Public repositories work without a token. A fetch usually takes 10–40 seconds.</p>

      {running && <ol className="mt-4 flex flex-col gap-1 text-[13px]">
        {PIPELINE.map((name, index) => <li key={name} className={index < step ? "text-ink-2" : index === step ? "text-ink font-medium" : "text-muted"}>
          <span className="inline-block w-5 font-mono">{index < step ? "✓" : index === step ? "›" : ""}</span>{name}
        </li>)}
      </ol>}
      {error && <div className="mt-4"><Notice tone="bad">{error}</Notice></div>}
      {latest && <div className="mt-4 flex flex-col gap-3">
        <PipelineLog summary={latest} />
        <div className="flex gap-2 flex-wrap">
          <Button variant="primary" onClick={() => open(latest.repository)}>Open overview</Button>
          <Button onClick={() => open(latest.repository, "/failures")}>Investigate failures</Button>
          <Button onClick={() => open(latest.repository, "/assistant")}>Ask the codebase</Button>
        </div>
      </div>}
    </Panel>

    <Panel flush title="Analysed repositories" aside={`${repositories.length}`}>
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-[13px]">
          <thead><tr>
            <th className={th}>Repository</th>
            <th className={`${th} text-right`}>Commits</th>
            <th className={`${th} text-right`}>CI runs</th>
            <th className={`${th} text-right`}>Chunks</th>
            <th className={`${th} text-right`}>Scored files</th>
            <th className={th}>Analysed</th>
            <th className={th}><span className="sr-only">Actions</span></th>
          </tr></thead>
          <tbody>
            {repositories.map((repo) => <tr key={repo.repository} className="hover:bg-paper">
              <td className={td}>
                <div className="flex items-center gap-2">
                  <span className="font-mono text-ink">{repo.repository}</span>
                  {isActive(repo) && <Badge tone="accent">active</Badge>}
                </div>
                <p className="text-[12px] text-muted mt-0.5">{repo.source}</p>
              </td>
              <td className={`${td} text-right font-mono`}>{repo.commits}</td>
              <td className={`${td} text-right font-mono`}>{repo.ciRuns}</td>
              <td className={`${td} text-right font-mono`}>{repo.indexedDocuments}</td>
              <td className={`${td} text-right font-mono`}>{repo.riskyFiles}</td>
              <td className={`${td} text-ink-2 whitespace-nowrap`}>{repo.source === "demo fixture" ? "–" : relativeTime(repo.analyzedAt)}</td>
              <td className={`${td} text-right whitespace-nowrap`}>
                <div className="inline-flex gap-1.5">
                  {!isActive(repo) && <Button onClick={() => open(repo.repository)}>Open</Button>}
                  {isActive(repo) && <Button variant="ghost" onClick={() => router.push("/")}>View</Button>}
                  {repo.source !== "demo fixture" && <Button variant="ghost" disabled={!!running} onClick={() => analyze(repo.repository, true)}>
                    {running === repo.repository ? "Fetching…" : "Re-fetch"}
                  </Button>}
                </div>
              </td>
            </tr>)}
          </tbody>
        </table>
      </div>
    </Panel>
  </div>;
}
