"use client";

import { useEffect, useState } from "react";
import FailuresFeed from "@/components/dashboard/FailuresFeed";
import { getOverview } from "@/lib/intelligenceApi";
import { Failure } from "@/types";

export default function FailuresPage() {
  const [failures, setFailures] = useState<Failure[]>([]);
  const [error, setError] = useState("");
  useEffect(() => { getOverview().then((data) => setFailures(data.failures)).catch((reason: Error) => setError(reason.message)); }, []);
  return <div>
    <h1 className="text-[19px] text-[#E7E9EC] mb-4">CI/CD Failures</h1>
    {error ? <p className="text-sm text-[#F0655A]">{error}</p> : failures.length ? <FailuresFeed items={failures} /> : <p className="text-sm text-[#8B93A1]">No failed demo deployments found.</p>}
  </div>;
}
