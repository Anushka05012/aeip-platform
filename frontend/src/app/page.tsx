"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import StatStrip from "@/components/dashboard/MetricCard";
import DeployChart from "@/components/dashboard/DeployChart";
import RiskList from "@/components/dashboard/RiskList";
import FailuresFeed from "@/components/dashboard/FailuresFeed";
import { Badge, Empty, Notice, PageHeader, Panel } from "@/components/ui";
import { formatDuration, utcTime } from "@/lib/format";
import { getOverview } from "@/lib/intelligenceApi";
import { IntelligenceOverview } from "@/types";

const more = "text-accent hover:underline underline-offset-2";

export default function OverviewPage() {
  const [data, setData] = useState<IntelligenceOverview | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { getOverview().then(setData).catch((reason: Error) => setError(reason.message)); }, []);

  if (error) return <><PageHeader title="Overview" /><Notice tone="bad">{error}</Notice></>;
  if (!data) return <><PageHeader title="Overview" meta="Loading repository data…" /></>;

  return <div className="flex flex-col gap-6">
    <PageHeader
      title="Overview"
      meta={<><span className="font-mono text-ink-2">{data.repository}</span> · {data.source} · {data.indexedDocuments} indexed chunks · last {data.windowDays} days</>}
    />

    <StatStrip metrics={data.metrics} />

    {!!data.incidents?.length && <Panel flush title="Recent incidents" aside={<Link className={more} href="/incidents">Timeline and root cause</Link>}>
      <ul className="divide-y divide-line">
        {data.incidents.slice(0, 3).map((item) => <li key={item.id}>
          <Link href={`/incidents?id=${item.id}`} className="flex items-center gap-3 px-4 py-2.5 hover:bg-paper flex-wrap">
            <Badge tone={item.status === "ongoing" ? "bad" : "good"}>{item.status}</Badge>
            <span className="text-[13.5px] font-medium text-ink">{item.title}</span>
            <span className="text-[12px] text-muted">{utcTime(item.start, true)} UTC · {formatDuration(item.durationMinutes)}</span>
            {item.rootCause && <span className="text-[12.5px] text-ink-2 ml-auto">
              <span className="text-muted">Cause:</span> {item.rootCause.title} <span className="text-muted">({item.rootCause.confidence})</span>
            </span>}
          </Link>
        </li>)}
      </ul>
    </Panel>}

    <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
      <Panel className="lg:col-span-3" title="CI runs per day" aside="default branch, push-triggered">
        <DeployChart data={data.deployTrend} />
      </Panel>
      <Panel className="lg:col-span-2" flush title="Riskiest files" aside={<Link className={more} href="/risk">All files</Link>}>
        {data.riskItems.length ? <RiskList items={data.riskItems.slice(0, 6)} /> : <Empty>No source files changed in this window.</Empty>}
      </Panel>
    </div>

    <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
      <Panel className="lg:col-span-3" flush title="Recent CI failures" aside={<Link className={more} href="/failures">Investigate</Link>}>
        {data.failures.length ? <FailuresFeed items={data.failures.slice(0, 5)} /> : <Empty>No failed runs.</Empty>}
      </Panel>
      <Panel className="lg:col-span-2" title="Risk summary">
        <p className="text-[13.5px] leading-6 text-ink-2">{data.summary}</p>
      </Panel>
    </div>
  </div>;
}
