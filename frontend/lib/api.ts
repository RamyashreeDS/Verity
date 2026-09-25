import type {
  DashboardResponse,
  HealthEvent,
  HealthSummary,
  HealingRecord,
  PipelineRun,
  EventType,
  ApiStatus,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

async function get<T>(path: string): Promise<T> {
  const res = await fetch(`${BASE}${path}`, { cache: "no-store" });
  if (!res.ok) throw new Error(`GET ${path} failed: ${res.status}`);
  return res.json();
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(`POST ${path} failed: ${res.status}`);
  return res.json();
}

export const api = {
  status: () => get<ApiStatus>("/api/status"),

  dashboard: () => get<DashboardResponse>("/api/dashboard"),

  entityHistory: (entity: string) =>
    get<{ entity: string; claims: unknown[] }>(`/api/dashboard/entity/${encodeURIComponent(entity)}/history`),

  conflicted: () =>
    get<{ entries: DashboardResponse["entries"]; count: number }>("/api/dashboard/conflicted"),

  generateVisual: () => get<{ image_url: string; prompt: string }>("/api/dashboard/visual"),

  healthEvents: (openOnly = true) =>
    get<{ events: HealthEvent[]; count: number }>(`/api/health/events?open_only=${openOnly}`),

  healthSummary: () => get<HealthSummary>("/api/health/summary"),

  healingRecords: () =>
    get<{ records: HealingRecord[]; total: number; committed: number; rolled_back: number }>(
      "/api/health/healing/records"
    ),

  startPipeline: (params: {
    event_type: EventType;
    location: string;
    radius_km?: number;
    time_window_hours?: number;
    keywords?: string[];
  }) => post<{ run_id: string; status: string }>("/api/pipeline/run", params),

  getPipelineRun: (runId: string) => get<PipelineRun>(`/api/pipeline/run/${runId}`),

  listRuns: () => get<PipelineRun[]>("/api/pipeline/runs"),
};
