import { screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import StatsPage from "../src/pages/StatsPage";
import { renderWithRouter, stubFetch } from "./helpers";

const STATS = {
  total: 8,
  by_category: { water: 4, electricity: 2, sanitation: 1, roads: 1, streetlights: 0, other: 0 },
  by_priority: { high: 3, normal: 4, low: 1 },
  by_status: { open: 5, in_progress: 2, resolved: 1, rejected: 0 },
  fallback_rate: 0.25,
  generated_at: "2026-09-20T07:00:00+00:00",
};

const PROVIDERS = {
  active_provider: "llm:groq",
  configured: "llm",
  fallback_provider: "rules",
  triage_cache_hit_rate: 0.5,
  recent: [
    { provider: "llm:groq", latency_ms: 640, fallback: false, cached: false, at: "2026-09-20T07:00:00+00:00" },
  ],
};

describe("Overview", () => {
  it("reports a cache miss as a fresh response", async () => {
    stubFetch([
      { body: STATS, headers: { "X-Cache": "MISS" } },
      { body: PROVIDERS },
    ]);
    renderWithRouter(<StatsPage />);

    expect(await screen.findByText("X-Cache: MISS")).toBeInTheDocument();
    expect(screen.getByText("fresh")).toBeInTheDocument();
  });

  it("reports a cache hit, and renders the aggregates", async () => {
    stubFetch([
      { body: STATS, headers: { "X-Cache": "HIT" } },
      { body: PROVIDERS },
    ]);
    renderWithRouter(<StatsPage />);

    expect(await screen.findByText("X-Cache: HIT")).toBeInTheDocument();
    expect(screen.getByText("cached")).toBeInTheDocument();
    expect(screen.getByText("8")).toBeInTheDocument();
    expect(screen.getByText("25%")).toBeInTheDocument();
    expect(screen.getAllByText("llm:groq").length).toBeGreaterThan(0);
  });
});
