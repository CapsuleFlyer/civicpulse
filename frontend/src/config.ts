/**
 * Runtime configuration.
 *
 * `import.meta.env` is deliberately not used: Vite inlines it into the bundle
 * at build time, so an API URL read that way would be frozen into the image and
 * the same artefact could not run in dev, CI and the cluster. The container
 * writes /config.js at start-up instead; in development the checked-in
 * public/config.js supplies the same shape.
 */
export type RuntimeConfig = {
  apiBaseUrl: string;
  environment: string;
  version: string;
};

const FALLBACK: RuntimeConfig = {
  apiBaseUrl: "/api",
  environment: "unknown",
  version: "unknown",
};

export function getConfig(): RuntimeConfig {
  const injected = (window as unknown as { __CIVICPULSE__?: Partial<RuntimeConfig> })
    .__CIVICPULSE__;
  return { ...FALLBACK, ...(injected ?? {}) };
}
