export type EventType = "wildfire" | "flood" | "earthquake" | "hurricane" | "accident";
export type SourceType = "official" | "news" | "social" | "crawled";
export type EntityType = "road" | "shelter" | "evacuation_zone" | "fire" | "flood" | "utility" | "weather";
export type WorldStateStatus = "confirmed" | "low_confidence" | "unresolved" | "conflicted" | "stale";
export type HealthEventType = "stale" | "contradiction" | "missing" | "loop" | "source_failure" | "source_degraded";
export type HealthSeverity = "low" | "medium" | "high" | "critical";
export type PipelineRunStatus = "pending" | "running" | "completed" | "failed";
export type HealingAction = "update_value" | "update_status" | "evict_claims" | "mark_unresolvable" | "request_resense" | "suppress_source";

export interface WorldStateEntry {
  entity: string;
  entity_type: EntityType;
  claim_type: string;
  current_value: string;
  confidence: number;
  status: WorldStateStatus;
  last_claim_id: string;
  last_updated: string;
  conflicting_claim_id?: string;
}

export interface HealthEvent {
  id: string;
  type: HealthEventType;
  severity: HealthSeverity;
  entity?: string;
  entity_type?: string;
  claim_type?: string;
  description: string;
  detected_at: string;
  context: Record<string, unknown>;
  resolved: boolean;
  resolved_at?: string;
}

export interface HealingRecord {
  id: string;
  health_event_id: string;
  diagnosed_cause_type: string;
  proposed_action: string;
  action_detail: Record<string, unknown>;
  lfm_reasoning: string;
  verify_passed: boolean;
  test_passed: boolean;
  committed: boolean;
  committed_at?: string;
  rolled_back: boolean;
  rolled_back_reason?: string;
}

export interface PipelineStageResult {
  stage: string;
  status: string;
  count: number;
  detail: string;
  started_at?: string;
  completed_at?: string;
}

export interface PipelineRun {
  id: string;
  query: {
    id: string;
    event_type: EventType;
    location: string;
    radius_km: number;
    time_window_hours: number;
    keywords: string[];
  };
  status: PipelineRunStatus;
  stages: PipelineStageResult[];
  started_at: string;
  completed_at?: string;
  error?: string;
}

export interface DashboardResponse {
  entries: WorldStateEntry[];
  last_updated?: string;
  active_run_id?: string;
}

export interface HealthSummary {
  open_event_count: number;
  severity_breakdown: Record<string, number>;
  type_breakdown: Record<string, number>;
  healing_committed: number;
  healing_rolled_back: number;
}

export interface ApiStatus {
  nimble: boolean;
  liquid_ai: boolean;
  tinybird: boolean;
  bfl: boolean;
}
