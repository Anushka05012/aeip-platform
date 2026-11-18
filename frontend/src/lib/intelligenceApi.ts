import { AssistantAnswer, CauseVerdict, FailureExplanation, IncidentDetail, IncidentSummary, IntelligenceOverview, RepositorySummary, RiskModel } from "@/types";

// Same-origin backend-for-frontend (src/app/api/aeip): it adds auth and forwards to INTELLIGENCE_API_URL.
const baseUrl = "/api/aeip";
const ACTIVE_KEY = "aeip.activeRepository";
export const ACTIVE_EVENT = "aeip:repository-changed";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
    });
  } catch {
    throw new Error("The intelligence service is not running. Start it with: python scripts/serve.py");
  }
  const body = await response.json().catch(() => ({}));
  if (response.status === 401 && typeof window !== "undefined") {
    // A full page load is intended here: proxy.ts must see the request to start sign-in.
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = `/login?next=${encodeURIComponent(window.location.pathname)}`;
  }
  if (!response.ok) throw new Error(body.error ?? "The intelligence service is unavailable.");
  return body as T;
}

/** The repository every page shows; chosen on the Repositories page. */
export function getActiveRepository(): string {
  try {
    return localStorage.getItem(ACTIVE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function setActiveRepository(repository: string) {
  try {
    localStorage.setItem(ACTIVE_KEY, repository);
  } catch {
    // Storage can be unavailable (private mode); the event still updates open pages.
  }
  window.dispatchEvent(new CustomEvent(ACTIVE_EVENT, { detail: repository }));
}

export function getOverview(repository = getActiveRepository()): Promise<IntelligenceOverview> {
  const query = repository ? `?repository=${encodeURIComponent(repository)}` : "";
  return request<IntelligenceOverview>(`/api/intelligence/demo${query}`);
}

export function getHealth(): Promise<{ status: string; llm: "groq" | "offline" }> {
  return request("/health");
}

export function listRepositories(): Promise<{ repositories: RepositorySummary[] }> {
  return request("/api/repositories");
}

export function analyzeRepository(repository: string, refresh = false): Promise<RepositorySummary> {
  return request<RepositorySummary>("/api/repositories/analyze", {
    method: "POST",
    body: JSON.stringify({ repository, refresh }),
  });
}

export function explainFailure(runId: string, repository = getActiveRepository(), refresh = false): Promise<FailureExplanation> {
  return request<FailureExplanation>("/api/failures/explain", {
    method: "POST",
    body: JSON.stringify({ runId, repository: repository || undefined, refresh }),
  });
}

export function askAssistant(question: string, repository = getActiveRepository()): Promise<AssistantAnswer> {
  return request<AssistantAnswer>("/api/assistant", {
    method: "POST",
    body: JSON.stringify({ question, repository: repository || undefined }),
  });
}

export function listIncidents(repository = getActiveRepository()): Promise<{
  repository: string; eventsBySource: Record<string, number>; incidents: IncidentSummary[];
}> {
  const query = repository ? `?repository=${encodeURIComponent(repository)}` : "";
  return request(`/api/incidents${query}`);
}

/** Confirm or reject a root-cause candidate; confirmed causes teach the repository's risk model. */
export function sendCauseFeedback(incidentId: string, ref: string, verdict: CauseVerdict,
  repository = getActiveRepository()): Promise<{ feedback: Record<string, CauseVerdict>; files: string[]; riskModel: RiskModel | null }> {
  return request("/api/incidents/feedback", {
    method: "POST",
    body: JSON.stringify({ incidentId, ref, verdict, repository: repository || undefined }),
  });
}

export function getIncident(id: string, useAi = false, repository = getActiveRepository()): Promise<IncidentDetail> {
  const params = new URLSearchParams({ id, ...(repository ? { repository } : {}), ...(useAi ? { ai: "1" } : {}) });
  return request<IncidentDetail>(`/api/incidents?${params}`);
}
