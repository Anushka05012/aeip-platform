"use client";

import { useEffect, useState } from "react";
import { RiskTable } from "@/components/dashboard/RiskList";
import { Empty, Notice, PageHeader, Panel } from "@/components/ui";
import { getOverview } from "@/lib/intelligenceApi";
import { IntelligenceOverview } from "@/types";

export default function RiskPage() {
  const [data, setData] = useState<IntelligenceOverview | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { getOverview().then(setData).catch((reason: Error) => setError(reason.message)); }, []);

  return <div className="flex flex-col gap-6">
    <PageHeader
      title="Change risk"
      meta={data ? <>Files changed in the last {data.windowDays} days, scored 0–100 from how they change, whether tests keep up, and how much else depends on them.</> : "Loading…"}
    />
    {error && <Notice tone="bad">{error}</Notice>}
    {data && <>
      <Panel title="Summary">
        <p className="text-[13.5px] leading-6 text-ink-2 max-w-[80ch]">{data.summary}</p>
      </Panel>
      <Panel flush title="Scored files" aside={`${data.riskItems.length} files`}>
        {data.riskItems.length ? <RiskTable items={data.riskItems} /> : <Empty>No source files changed in the analysis window.</Empty>}
      </Panel>
      <p className="text-[12px] text-muted leading-5">
        Score = change frequency (30, capped at 10 changes) + lines churned (25, capped at 500) + complexity growth (15, capped at +50 branches)
        + test gap (15 with no test file; up to 7 when changes skip the tests) + blast radius (10, capped at 10 importing files)
        + dependency update in the same commit (5). High ≥ 70, medium ≥ 40. Hover a score for its breakdown. Tests, docs, config and lock files are not scored.
      </p>
    </>}
  </div>;
}
