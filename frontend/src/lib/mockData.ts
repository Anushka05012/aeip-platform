import { Metric, RiskItem, Failure, DeployPoint, ChatMessage } from "@/types";

export const metrics: Metric[] = [
    { label: "Deployment frequency", value: "10.2", unit: "/day", delta: "+18%", up: true },
    { label: "Lead time for changes", value: "3.4", unit: "hrs", delta: "-22%", up: true },
    { label: "Change failure rate", value: "8.1", unit: "%", delta: "+2.1%", up: false },
    { label: "Mean time to recovery", value: "41", unit: "min", delta: "-9%", up: true },
];

export const deployTrend: DeployPoint[] = [
    { d: "Sep 8", v: 4 },
    { d: "Sep 9", v: 6 },
    { d: "Sep 10", v: 5 },
    { d: "Sep 11", v: 8 },
    { d: "Sep 12", v: 7 },
    { d: "Sep 13", v: 9 },
    { d: "Sep 14", v: 11 },
    { d: "Sep 15", v: 10 },
];

export const riskItems: RiskItem[] = [
    { file: "services/ingestion/webhook-handler.ts", score: 92, reason: "12 changes in 48h, no test coverage" },
    { file: "lib/embeddings/chunker.py", score: 78, reason: "High churn, touched by 3 authors" },
    { file: "api/routes/failure-controller.ts", score: 65, reason: "Complexity spike after last merge" },
    { file: "components/dashboard/RiskHeatmap.tsx", score: 41, reason: "Minor churn, stable history" },
];

export const failures: Failure[] = [
    { id: "m1", commit: "", workflow: "CI", event: "push", repo: "aeip-platform", branch: "feature/rag-engine-anushka", cause: "Timeout connecting to pgvector during embedding batch", time: "14m ago", severity: "high" },
    { id: "m2", commit: "", workflow: "CI", event: "push", repo: "aeip-platform", branch: "feature/ingestion-github-snehal", cause: "Webhook signature verification failed", time: "1h ago", severity: "medium" },
    { id: "m3", commit: "", workflow: "CI", event: "push", repo: "aeip-platform", branch: "main", cause: "Type mismatch in DORA metrics aggregator", time: "3h ago", severity: "low" },
];

export const initialChat: ChatMessage[] = [
    { role: "user", content: "Why did the ingestion job fail on webhook-handler.ts?" },
    { role: "assistant", content: "Signature verification threw before payload parsing — the secret env var wasn't loaded in the worker context." },
];