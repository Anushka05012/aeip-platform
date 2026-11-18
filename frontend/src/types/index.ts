export type Severity = "high" | "medium" | "low";

export type Metric = { label: string; value: string; unit: string; delta: string; up: boolean };
export type DeployPoint = { d: string; v: number };
export type RiskItem = {
  file: string; score: number; reason: string;
  level?: string; changes?: number; churn?: number; complexity?: number;
  hasTests?: boolean; testTouchRatio?: number; dependents?: number; dependencyChanges?: number;
  pastFixes?: number;
  breakdown?: RiskBreakdown;
  /** From the repository's learned model, once it has enough labels (see RiskModel). */
  learned?: { probability: number; drivers: string[] } | null;
};
/** What AEIP has learned about which changes break this repository. */
export type RiskModel = {
  active: boolean; labels: number; incidentLabels: number; bugFixLabels: number; examples: number;
  needed: number; message: string; weights: { signal: string; weight: number }[];
};
export type CauseVerdict = "confirmed" | "rejected";
export type RiskBreakdown = {
  frequency: number; churn: number; complexity: number; testGap: number; blastRadius: number; dependencies: number;
};
export type Failure = {
  id: string; commit: string; workflow: string; event: string;
  repo: string; branch: string; cause: string; time: string; severity: Severity;
  flaky?: boolean; // the same workflow also passed on this exact commit
};

export type FlakyWorkflow = {
  workflow: string; runs: number; failures: number; flips: number; flipRate: number;
  level: "flaky" | "suspected";
  events: { kind: string; commit: string; failedRuns: string[]; passedRuns: string[]; detail: string }[];
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
  flaky?: FlakyWorkflow[];
  incidents?: IncidentSummary[];
  riskModel?: RiskModel | null;
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
export type RootCause = {
  kind: "deploy" | "migration" | "config" | "commit";
  title: string; time: string; ref: string; service: string;
  score: number; confidence: "likely" | "possible" | "weak";
  signals: Partial<Record<"files" | "timing" | "recovery" | "type" | "service" | "risk", number>>;
  evidence: string[];
  commits: { sha: string; message: string; files: string[] }[];
  files: string[];
  rolledBackAt: string | null;
};

export type IncidentSummary = {
  id: string; title: string; start: string; end: string; durationMinutes: number;
  status: "resolved" | "ongoing"; severity: string; services: string[]; sources: string[];
  errorCount: number; distinctErrors: number; rootCause: RootCause | null;
};

export type TimelineEntry = {
  time: string; source: string; kind: string; title: string; severity: string; service: string;
  environment: string; commit: string; files: string[]; fingerprint: string; ref: string; url: string; message: string;
};

export type IncidentDetail = IncidentSummary & {
  candidates: RootCause[]; timeline: TimelineEntry[]; narrative: string; nextSteps: string[];
  narrativeMode: "rules" | "groq";
  /** Engineers' verdicts on the candidates, by candidate ref. */
  feedback?: Record<string, CauseVerdict>;
};
