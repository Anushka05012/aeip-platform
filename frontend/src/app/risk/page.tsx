"use client";

import { useEffect, useState } from "react";
import RiskList from "@/components/dashboard/RiskList";
import { getOverview } from "@/lib/intelligenceApi";
import { RiskItem } from "@/types";

export default function RiskPage() {
  const [risks, setRisks] = useState<RiskItem[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { getOverview().then((data) => setRisks(data.riskItems)).catch((reason: Error) => setError(reason.message)); }, []);
  return <div>
    <h1 className="text-[19px] text-[#E7E9EC] mb-4">Risk Intelligence</h1>
    {error ? <p className="text-sm text-[#F0655A]">{error}</p> : <div className="max-w-md">{risks.length ? <RiskList items={risks} /> : <p className="text-sm text-[#8B93A1]">Loading calculated risk scores...</p>}</div>}
  </div>;
}
