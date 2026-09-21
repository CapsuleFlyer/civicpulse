import { useCallback, useEffect, useState } from "react";
import { ApiError, getProviders, getStats } from "../api/client";
import type { Providers, Stats } from "../api/types";
import Working from "../components/Working";

function Bars({ counts, total }: { counts: Record<string, number>; total: number }) {
  return (
    <div className="bars">
      {Object.entries(counts).map(([key, count]) => (
        <div className="bar" key={key}>
          <span>{key.replace("_", " ")}</span>
          <span className="bar__track">
            <span
              className="bar__fill"
              data-key={key}
              style={{ width: total > 0 ? `${Math.round((count / total) * 100)}%` : "0%" }}
            />
          </span>
          <span className="bar__count">{count}</span>
        </div>
      ))}
    </div>
  );
}

export default function StatsPage() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [cache, setCache] = useState<"HIT" | "MISS" | "unknown">("unknown");
  const [providers, setProviders] = useState<Providers | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const [statsResult, providersResult] = await Promise.all([getStats(), getProviders()]);
      setStats(statsResult.stats);
      setCache(statsResult.cache);
      setProviders(providersResult);
      setError(null);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught.message : "The overview could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <div className="page stack">
      <div>
        <h1>Overview</h1>
        <p className="page__lede">
          Aggregates are cached for 30 seconds and cleared whenever a complaint is written, so this
          page is never more than one write behind.
        </p>
      </div>

      {error && (
        <p className="notice" role="alert">
          {error}
        </p>
      )}
      {loading && <Working>Loading aggregates…</Working>}

      {stats && (
        <>
          <section className="panel">
            <div className="figure">
              <div>
                <div className="figure__number">{stats.total}</div>
                <div className="receipt__label">reports on record</div>
              </div>
              <div>
                <div className="figure__number">{Math.round(stats.fallback_rate * 100)}%</div>
                <div className="receipt__label">triaged by the fallback rules</div>
              </div>
              {providers && (
                <div>
                  <div className="figure__number">
                    {Math.round(providers.triage_cache_hit_rate * 100)}%
                  </div>
                  <div className="receipt__label">duplicate reports served from cache</div>
                </div>
              )}
            </div>
            <p style={{ marginTop: "1.25rem", marginBottom: 0 }}>
              <span className="cache-badge">
                This response: <b>{cache === "HIT" ? "cached" : cache === "MISS" ? "fresh" : "unknown"}</b>
                <span className="mono">X-Cache: {cache}</span>
              </span>{" "}
              <button className="button button--ghost button--small" type="button" onClick={() => void load()}>
                Reload
              </button>
            </p>
          </section>

          <section className="panel">
            <h2>By department</h2>
            <Bars counts={stats.by_category} total={stats.total} />
          </section>

          <section className="panel">
            <h2>By priority</h2>
            <Bars counts={stats.by_priority} total={stats.total} />
            <h2 style={{ marginTop: "1.5rem" }}>By status</h2>
            <Bars counts={stats.by_status} total={stats.total} />
          </section>
        </>
      )}

      {providers && (
        <section className="panel">
          <h2>Triage provider</h2>
          <p>
            Running <span className="mono">{providers.active_provider}</span>, configured as{" "}
            <span className="mono">{providers.configured}</span>, falling back to{" "}
            <span className="mono">{providers.fallback_provider}</span>.
          </p>
          <div className="table-scroll">
            <table style={{ minWidth: "32rem" }}>
              <thead>
                <tr>
                  <th scope="col">When</th>
                  <th scope="col">Provider</th>
                  <th scope="col">Latency</th>
                  <th scope="col">Served from</th>
                </tr>
              </thead>
              <tbody>
                {providers.recent.map((outcome, index) => (
                  <tr key={`${outcome.at}-${index}`}>
                    <td className="meta">{new Date(outcome.at).toLocaleTimeString()}</td>
                    <td className="mono">{outcome.provider}</td>
                    <td className="mono">{outcome.latency_ms} ms</td>
                    <td>{outcome.cached ? "cache" : outcome.fallback ? "fallback rules" : "model"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
