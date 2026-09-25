/**
 * The shapes the backend actually returns.
 *
 * These mirror the Pydantic models in backend/app/schemas.py. They are not
 * trusted to stay in step by good intentions: scripts/check_api_contract.py
 * runs in CI against the live /api/openapi.json and fails the build if an
 * operation, a status code or an enum member listed in api/contract.json has
 * drifted.
 */
export const CATEGORIES = [
  "water",
  "electricity",
  "sanitation",
  "roads",
  "streetlights",
  "other",
] as const;
export const PRIORITIES = ["high", "normal", "low"] as const;
export const STATUSES = ["open", "in_progress", "resolved", "rejected"] as const;

export type Category = (typeof CATEGORIES)[number];
export type Priority = (typeof PRIORITIES)[number];
export type Status = (typeof STATUSES)[number];

export type Complaint = {
  id: string;
  text: string;
  location: string;
  reporter_contact: string | null;
  category: Category;
  priority: Priority;
  status: Status;
  ai_summary: string | null;
  triaged_by: string;
  triage_latency_ms: number;
  created_at: string;
  updated_at: string;
};

export type Page<T> = {
  items: T[];
  total: number;
  page: number;
  page_size: number;
};

export type Stats = {
  total: number;
  by_category: Record<string, number>;
  by_priority: Record<string, number>;
  by_status: Record<string, number>;
  fallback_rate: number;
  generated_at: string;
};

export type TriageOutcome = {
  provider: string;
  latency_ms: number;
  fallback: boolean;
  cached: boolean;
  at: string;
};

export type Providers = {
  active_provider: string;
  configured: string;
  fallback_provider: string;
  triage_cache_hit_rate: number;
  recent: TriageOutcome[];
};

export type FieldError = { field: string; message: string };

export type ComplaintDraft = {
  text: string;
  location: string;
  reporter_contact?: string | null;
};

export type ComplaintFilters = {
  category?: Category | "";
  priority?: Priority | "";
  status?: Status | "";
  page?: number;
  page_size?: number;
};
