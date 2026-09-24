"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import StatStrip from "@/components/dashboard/MetricCard";
import DeployChart from "@/components/dashboard/DeployChart";
import RiskList from "@/components/dashboard/RiskList";
import FailuresFeed from "@/components/dashboard/FailuresFeed";
import { Empty, Notice, PageHeader, Panel } from "@/components/ui";
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
