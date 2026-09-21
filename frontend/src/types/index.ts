export type Severity = "high" | "medium" | "low";

export type Metric = { label: string; value: string; unit: string; delta: string; up: boolean };
export type DeployPoint = { d: string; v: number };
export type RiskItem = { file: string; score: number; reason: string };
export type Failure = { repo: string; branch: string; cause: string; time: string; severity: Severity };
export type ChatMessage = { role: "user" | "assistant"; content: string };
export type Evidence = { path: string; score: number; content?: string };

export type IntelligenceOverview = {
  repository: string;
  indexedDocuments: number;
  metrics: Metric[];
  deployTrend: DeployPoint[];
  riskItems: RiskItem[];
  failures: Failure[];
  summary: string;
  evidence: Evidence[];
};

export type AssistantAnswer = {
  answer: string;
  risk: { file: string; score: number; level: string; reasons: string[] };
  evidence: Evidence[];
  mode: "offline" | "groq";
};
