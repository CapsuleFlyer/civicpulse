import { STATUSES, type Complaint, type Status } from "../api/types";
import { label } from "./Tag";

/**
 * Every status other than the current one is offered.
 *
 * This looks wrong until you remember where the state machine lives: putting
 * the legal transitions in React would make two sources of truth, and the copy
 * in the browser is the one that rots. The server rejects an illegal move with
 * a 409 that names it, and the dashboard shows that message.
 */
export default function StatusActions({
  complaint,
  onChange,
  busy,
}: {
  complaint: Complaint;
  onChange: (status: Status) => void;
  busy: boolean;
}) {
  return (
    <div style={{ display: "flex", gap: "0.35rem", flexWrap: "wrap" }}>
      {STATUSES.filter((status) => status !== complaint.status).map((status) => (
        <button
          key={status}
          type="button"
          className="button button--ghost button--small"
          disabled={busy}
          onClick={() => onChange(status)}
        >
          {label(status)}
        </button>
      ))}
    </div>
  );
}
