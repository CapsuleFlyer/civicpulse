import { getConfig } from "../config";
import type {
  Complaint,
  ComplaintDraft,
  ComplaintFilters,
  FieldError,
  Page,
  Providers,
  Stats,
  Status,
} from "./types";

/** An error the server described. `message` is rendered to the operator verbatim. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fields: FieldError[];
  readonly retryAfter: number | null;

  constructor(
    status: number,
    code: string,
    message: string,
    fields: FieldError[] = [],
    retryAfter: number | null = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fields = fields;
    this.retryAfter = retryAfter;
  }
}

type ErrorBody = {
  error?: string;
  message?: string;
  fields?: FieldError[];
  retry_after?: number;
};

async function request<T>(path: string, init?: RequestInit): Promise<{ data: T; response: Response }> {
  const { apiBaseUrl } = getConfig();
  let response: Response;
  try {
    response = await fetch(`${apiBaseUrl}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError(0, "network_error", "The server could not be reached. Check your connection and try again.");
  }

  if (!response.ok) {
    let body: ErrorBody = {};
    try {
      body = (await response.json()) as ErrorBody;
    } catch {
      body = {};
    }
    const retryHeader = response.headers.get("Retry-After");
    throw new ApiError(
      response.status,
      body.error ?? "http_error",
      body.message ?? `The server returned ${response.status}.`,
      body.fields ?? [],
      retryHeader ? Number(retryHeader) : (body.retry_after ?? null),
    );
  }

  return { data: (await response.json()) as T, response };
}

export async function createComplaint(draft: ComplaintDraft): Promise<Complaint> {
  const { data } = await request<Complaint>("/complaints", {
    method: "POST",
    body: JSON.stringify(draft),
  });
  return data;
}

export async function listComplaints(filters: ComplaintFilters = {}): Promise<Page<Complaint>> {
  const params = new URLSearchParams();
  if (filters.category) params.set("category", filters.category);
  if (filters.priority) params.set("priority", filters.priority);
  if (filters.status) params.set("status", filters.status);
  params.set("page", String(filters.page ?? 1));
  params.set("page_size", String(filters.page_size ?? 10));
  const { data } = await request<Page<Complaint>>(`/complaints?${params.toString()}`);
  return data;
}

export async function updateStatus(id: string, status: Status): Promise<Complaint> {
  const { data } = await request<Complaint>(`/complaints/${id}/status`, {
    method: "PATCH",
    body: JSON.stringify({ status }),
  });
  return data;
}

/** The cache state travels with the payload: the dashboard shows it. */
export async function getStats(): Promise<{ stats: Stats; cache: "HIT" | "MISS" | "unknown" }> {
  const { data, response } = await request<Stats>("/stats");
  const header = response.headers.get("X-Cache");
  const cache = header === "HIT" || header === "MISS" ? header : "unknown";
  return { stats: data, cache };
}

export async function getProviders(): Promise<Providers> {
  const { data } = await request<Providers>("/meta/providers");
  return data;
}
