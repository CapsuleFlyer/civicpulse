import "@testing-library/jest-dom/vitest";
import { cleanup } from "@testing-library/react";
import { afterEach, vi } from "vitest";

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

// The runtime config normally arrives from /config.js, written by the
// container entrypoint. Tests supply it directly.
(window as unknown as { __CIVICPULSE__: unknown }).__CIVICPULSE__ = {
  apiBaseUrl: "/api",
  environment: "test",
  version: "test",
};
