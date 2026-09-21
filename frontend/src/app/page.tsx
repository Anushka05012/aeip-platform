"use client";

import { useEffect, useState } from "react";
import MetricCard from "@/components/dashboard/MetricCard";
import DeployChart from "@/components/dashboard/DeployChart";
import RiskList from "@/components/dashboard/RiskList";
import FailuresFeed from "@/components/dashboard/FailuresFeed";
import { getOverview } from "@/lib/intelligenceApi";
import { IntelligenceOverview } from "@/types";

export default function OverviewPage() {
  const [data, setData] = useState<IntelligenceOverview | null>(null);
  const [error, setError] = useState("");
  useEffect(() => { getOverview().then(setData).catch((reason: Error) => setError(reason.message)); }, []);

  if (error) return <p className="text-sm text-[#F0655A]">Intelligence service: {error}</p>;
  if (!data) return <p className="text-sm text-[#8B93A1]">Loading live intelligence data...</p>;

  return <div className="flex flex-col gap-7">
    <div>
      <h1 className="text-[19px] text-[#E7E9EC] mb-1">Engineering overview</h1>
      <p className="text-xs text-[#8B93A1] mb-4">Live local RAG demo · {data.repository} · {data.indexedDocuments} indexed documents</p>
      <div className="grid grid-cols-4 gap-4">{data.metrics.map((metric) => <MetricCard key={metric.label} m={metric} />)}</div>
    </div>
    <div className="grid grid-cols-3 gap-5">
      <div className="col-span-2"><DeployChart data={data.deployTrend} /></div>
      <RiskList items={data.riskItems} />
    </div>
    <div className="grid grid-cols-3 gap-5">
      <div className="col-span-2"><FailuresFeed items={data.failures} /></div>
      <div className="h-[280px] bg-[#12151C] border border-[#232833] rounded-md p-5">
        <p className="text-[13px] text-[#B4B9C2] mb-3">Evidence-grounded summary</p>
        <p className="text-[12.5px] leading-6 text-[#8B93A1]">{data.summary}</p>
      </div>
    </div>
  </div>;
}
