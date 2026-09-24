export type Severity = "high" | "medium" | "low";

export type Metric = { label: string; value: string; unit: string; delta: string; up: boolean };
export type DeployPoint = { d: string; v: number };
export type RiskItem = {
  file: string; score: number; reason: string;
  level?: string; changes?: number; churn?: number; complexity?: number;
};
export type Failure = {
  id: string; commit: string; workflow: string; event: string;
  repo: string; branch: string; cause: string; time: string; severity: Severity;
};

export type FailureExplanation = {
  run_id: string;
  workflow: string;
  branch: string;
  commit: string;
  commit_message: string;
  verdict: "related" | "unrelated" | "uncertain";
  category: string;
  confidence: number;
  needs_review: boolean;
  explanation: string;
  next_steps: string[];
  signals: string[];
  changed_files: { path: string; mentionedInLog: boolean; risk: number | null }[];
  error_lines: string[];
  evidence: Evidence[];
  failed_jobs: { name: string; failedSteps: string[] }[];
  log_source: string;
  mode: "groq" | "offline";
  notes: string[];
  cached: boolean;
  pull_request?: { number: number; title: string; state: string; base: string } | null;
};
export type ChatMessage = { role: "user" | "assistant"; content: string };
export type Evidence = { path: string; score: number; content?: string };

export type PipelineStage = { stage: string; detail: string; ms: number };

export type RepositorySummary = {
  repository: string;
  source: string;
  indexedDocuments: number;
  commits: number;
  ciRuns: number;
  pullRequests?: number;
  riskyFiles: number;
  analyzedAt: string;
  stages: PipelineStage[];
};

export type IntelligenceOverview = {
  repository: string;
  source: string;
  indexedDocuments: number;
  metrics: Metric[];
  deployTrend: DeployPoint[];
  riskItems: RiskItem[];
  failures: Failure[];
  summary: string;
  windowDays: number;
  evidence: Evidence[];
};

export type AssistantAnswer = {
  answer: string;
  risk: { file: string; score: number; level: string; reasons: string[] } | null;
  evidence: Evidence[];
  mode: "offline" | "groq";
};

export type Repository = {
  id: string;
  name: string;
  owner: string;
  fullName: string;
  url: string;
  createdAt: string;
  _count: { commits: number; pullRequests: number };
};

export type IngestResult = {
  repository: string;
  repositoryId: string;
  commitsIngested: number;
  pullRequestsIngested: number;
};