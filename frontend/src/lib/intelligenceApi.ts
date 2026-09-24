import { AssistantAnswer, FailureExplanation, IntelligenceOverview, RepositorySummary } from "@/types";

const baseUrl = process.env.NEXT_PUBLIC_INTELLIGENCE_API_URL ?? "http://localhost:8001";
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
