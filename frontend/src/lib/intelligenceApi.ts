import { AssistantAnswer, IntelligenceOverview } from "@/types";

const baseUrl = process.env.NEXT_PUBLIC_INTELLIGENCE_API_URL ?? "http://localhost:8001";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error ?? "The intelligence service is unavailable.");
  return body as T;
}

export function getOverview(): Promise<IntelligenceOverview> {
  return request<IntelligenceOverview>("/api/intelligence/demo");
}

export function askAssistant(question: string): Promise<AssistantAnswer> {
  return request<AssistantAnswer>("/api/assistant", { method: "POST", body: JSON.stringify({ question }) });
}
