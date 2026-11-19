import type { ChatResponse, SessionSummary } from "./types";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    ...init,
  });
  if (!response.ok) {
    const detail = await response.text();
    throw new Error(detail || `Request failed (${response.status})`);
  }
  return response.json() as Promise<T>;
}

export function sendMessage(message: string, sessionId: string | null, sourceFilter: string | null) {
  return request<ChatResponse>("/api/chat", {
    method: "POST",
    body: JSON.stringify({
      message,
      session_id: sessionId,
      source_filter: sourceFilter,
    }),
  });
}

export function listSessions() {
  return request<{ sessions: SessionSummary[] }>("/api/chat/history");
}

export function getSession(sessionId: string) {
  return request<{ messages: Array<{ id: string; role: "user" | "assistant"; content: string; payload?: ChatResponse | null }> }>(
    `/api/chat/history?session_id=${encodeURIComponent(sessionId)}`,
  );
}

export function deleteSession(sessionId: string) {
  return request<{ deleted: boolean }>(`/api/chat/history/${sessionId}`, { method: "DELETE" });
}

export function getStats() {
  return request<{
    records: number;
    by_source: Record<string, number>;
    index_ready: boolean;
    llm_configured: boolean;
    last_scrape: { finished_at?: string | null; report?: { last_successful_scrape?: string | null } } | null;
  }>("/api/stats");
}
