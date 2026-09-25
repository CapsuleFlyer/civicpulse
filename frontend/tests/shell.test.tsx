import type React from "react";
import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import ErrorBoundary from "../src/components/ErrorBoundary";
import { getConfig } from "../src/config";
import { validateDraft } from "../src/validation";

describe("runtime configuration", () => {
  it("reads the API base injected at container start-up", () => {
    expect(getConfig().apiBaseUrl).toBe("/api");
  });

  it("falls back to a relative path when /config.js did not load", () => {
    const original = (window as unknown as { __CIVICPULSE__?: unknown }).__CIVICPULSE__;
    (window as unknown as { __CIVICPULSE__?: unknown }).__CIVICPULSE__ = undefined;
    expect(getConfig().apiBaseUrl).toBe("/api");
    (window as unknown as { __CIVICPULSE__?: unknown }).__CIVICPULSE__ = original;
  });
});

describe("client-side validation mirrors the server", () => {
  it("accepts a well-formed draft", () => {
    expect(
      validateDraft({
        text: "Open manhole near the school gate since last week.",
        location: "H-9, Islamabad",
        reporter_contact: "",
      }),
    ).toEqual({});
  });

  it("rejects a location that is too short", () => {
    const errors = validateDraft({
      text: "Open manhole near the school gate since last week.",
      location: "H",
      reporter_contact: "",
    });
    expect(errors.location).toMatch(/street, sector or landmark/i);
  });
});

describe("error boundary", () => {
  it("explains the failure instead of showing a blank page", () => {
    vi.spyOn(console, "error").mockImplementation(() => {});
    const Exploding = (): React.ReactElement => {
      throw new Error("render exploded");
    };
    render(
      <ErrorBoundary>
        <Exploding />
      </ErrorBoundary>,
    );
    expect(screen.getByText(/this screen stopped working/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reload the page/i })).toBeInTheDocument();
  });
});
