import { IngestResult, Repository } from "@/types";

const baseUrl = process.env.NEXT_PUBLIC_INGESTION_API_URL ?? "http://localhost:4000";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${baseUrl}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...init?.headers },
  });
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(body.error ?? "The ingestion service is unavailable.");
  return body as T;
}

export function addRepository(owner: string, repo: string): Promise<IngestResult> {
  return request<IngestResult>("/api/repositories", {
    method: "POST",
    body: JSON.stringify({ owner, repo }),
  });
}

export function listRepositories(): Promise<Repository[]> {
  return request<Repository[]>("/api/repositories");
}