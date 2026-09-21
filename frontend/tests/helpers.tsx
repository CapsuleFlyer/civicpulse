import { MemoryRouter } from "react-router-dom";
import { render } from "@testing-library/react";
import type { ReactElement } from "react";
import type { Complaint } from "../src/api/types";

export function renderWithRouter(ui: ReactElement) {
  return render(<MemoryRouter>{ui}</MemoryRouter>);
}

export function complaint(overrides: Partial<Complaint> = {}): Complaint {
  return {
    id: "1f2e3d4c-5b6a-4978-8695-a4b3c2d1e0f9",
    text: "Burst water main flooding Street 12 since fajr, water entering ground floors.",
    location: "Street 12, G-9/1, Islamabad",
    reporter_contact: null,
    category: "water",
    priority: "high",
    status: "open",
    ai_summary: "Water issue at Street 12: burst main flooding since dawn.",
    triaged_by: "llm:groq",
    triage_latency_ms: 812,
    created_at: "2026-09-20T06:30:00+00:00",
    updated_at: "2026-09-20T06:30:00+00:00",
    ...overrides,
  };
}

type FetchReply = { status?: number; body?: unknown; headers?: Record<string, string> };

/** Installs a fetch stub that replies per URL fragment, in call order. */
export function stubFetch(replies: FetchReply[]) {
  const queue = [...replies];
  const stub = vi.fn(async () => {
    const reply = queue.shift() ?? { status: 200, body: {} };
    return new Response(JSON.stringify(reply.body ?? {}), {
      status: reply.status ?? 200,
      headers: { "Content-Type": "application/json", ...(reply.headers ?? {}) },
    });
  });
  vi.stubGlobal("fetch", stub);
  return stub;
}
