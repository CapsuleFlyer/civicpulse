import { useCallback, useEffect, useState } from "react";
import { ApiError, listComplaints, updateStatus } from "../api/client";
import {
  CATEGORIES,
  PRIORITIES,
  STATUSES,
  type Complaint,
  type ComplaintFilters,
  type Status,
} from "../api/types";
import StatusActions from "../components/StatusActions";
import Tag from "../components/Tag";
import Working from "../components/Working";

const PAGE_SIZE = 10;

function formatWhen(iso: string): string {
  return new Date(iso).toLocaleString(undefined, {
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export default function DashboardPage() {
  const [filters, setFilters] = useState<ComplaintFilters>({ page: 1, page_size: PAGE_SIZE });
  const [rows, setRows] = useState<Complaint[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const page = await listComplaints(filters);
      setRows(page.items);
      setTotal(page.total);
    } catch (error) {
      setMessage(error instanceof ApiError ? error.message : "The queue could not be loaded.");
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void load();
  }, [load]);

  async function advance(complaint: Complaint, status: Status) {
    setBusyId(complaint.id);
    setMessage(null);
    try {
      const updated = await updateStatus(complaint.id, status);
      setRows((current) => current.map((row) => (row.id === updated.id ? updated : row)));
    } catch (error) {
      // A 409 is the state machine talking. Show exactly what it said, not a
      // generic failure: "cannot transition from resolved to open" is the whole
      // answer the operator needs.
      setMessage(error instanceof ApiError ? error.message : "The status could not be changed.");
    } finally {
      setBusyId(null);
    }
  }

  function update(patch: Partial<ComplaintFilters>) {
    setFilters((current) => ({ ...current, ...patch, page: patch.page ?? 1 }));
  }

  const page = filters.page ?? 1;
  const lastPage = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="page stack">
      <div>
        <h1>Operations queue</h1>
        <p className="page__lede">
          Everything reported, newest first. Advancing a status here is what the crews see.
        </p>
      </div>

      <div className="filters panel panel--quiet">
        <label>
          Department
          <select
            value={filters.category ?? ""}
            onChange={(event) => update({ category: event.target.value as ComplaintFilters["category"] })}
          >
            <option value="">All</option>
            {CATEGORIES.map((category) => (
              <option key={category} value={category}>
                {category}
              </option>
            ))}
          </select>
        </label>
        <label>
          Priority
          <select
            value={filters.priority ?? ""}
            onChange={(event) => update({ priority: event.target.value as ComplaintFilters["priority"] })}
          >
            <option value="">All</option>
            {PRIORITIES.map((priority) => (
              <option key={priority} value={priority}>
                {priority}
              </option>
            ))}
          </select>
        </label>
        <label>
          Status
          <select
            value={filters.status ?? ""}
            onChange={(event) => update({ status: event.target.value as ComplaintFilters["status"] })}
          >
            <option value="">All</option>
            {STATUSES.map((status) => (
              <option key={status} value={status}>
                {status}
              </option>
            ))}
          </select>
        </label>
        <button className="button button--ghost" type="button" onClick={() => void load()}>
          Refresh
        </button>
      </div>

      {message && (
        <p className="notice" role="alert">
          {message}
        </p>
      )}

      {loading && <Working>Loading the queue…</Working>}

      {!loading && rows.length === 0 && (
        <p className="panel panel--quiet">
          Nothing matches these filters. Clear them, or seed the database with{" "}
          <span className="mono">make seed</span>.
        </p>
      )}

      {rows.length > 0 && (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th scope="col">Reported</th>
                <th scope="col">Complaint</th>
                <th scope="col">Department</th>
                <th scope="col">Priority</th>
                <th scope="col">Status</th>
                <th scope="col">Triage</th>
                <th scope="col">Move to</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((complaint) => (
                <tr key={complaint.id}>
                  <td className="meta">{formatWhen(complaint.created_at)}</td>
                  <td className="text">
                    <div>{complaint.ai_summary ?? complaint.text}</div>
                    <div className="meta">{complaint.location}</div>
                  </td>
                  <td>{complaint.category}</td>
                  <td>
                    <Tag value={complaint.priority} />
                  </td>
                  <td>
                    <Tag value={complaint.status} />
                  </td>
                  <td className="mono">
                    {complaint.triaged_by}
                    <div>{complaint.triage_latency_ms} ms</div>
                  </td>
                  <td>
                    <StatusActions
                      complaint={complaint}
                      busy={busyId === complaint.id}
                      onChange={(status) => void advance(complaint, status)}
                    />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      <div className="pager">
        <button
          className="button button--ghost button--small"
          type="button"
          disabled={page <= 1}
          onClick={() => update({ page: page - 1 })}
        >
          Previous
        </button>
        <span className="pager__position">
          Page {page} of {lastPage} · {total} reports
        </span>
        <button
          className="button button--ghost button--small"
          type="button"
          disabled={page >= lastPage}
          onClick={() => update({ page: page + 1 })}
        >
          Next
        </button>
      </div>
    </div>
  );
}
