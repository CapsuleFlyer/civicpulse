import type { Complaint } from "../api/types";
import Tag from "./Tag";

const PROVIDER_NOTES: Record<string, string> = {
  "rules:fallback":
    "The model was unavailable, so the keyword classifier handled this one. An operator will confirm the category.",
  rules: "Classified by the keyword rules engine.",
};

/** What the citizen gets back: the decision, who made it, and how long it took. */
export default function TriageReceipt({ complaint }: { complaint: Complaint }) {
  const note = PROVIDER_NOTES[complaint.triaged_by];

  return (
    <section className="panel receipt" aria-labelledby="receipt-heading">
      <h2 id="receipt-heading">Logged as reference {complaint.id.slice(0, 8)}</h2>
      <div className="receipt__grid">
        <div>
          <div className="receipt__label">Department</div>
          <div className="receipt__value">{complaint.category}</div>
        </div>
        <div>
          <div className="receipt__label">Priority</div>
          <div className="receipt__value">
            <Tag value={complaint.priority} />
          </div>
        </div>
        <div>
          <div className="receipt__label">Status</div>
          <div className="receipt__value">
            <Tag value={complaint.status} />
          </div>
        </div>
        <div>
          <div className="receipt__label">Triaged by</div>
          <div className="receipt__value mono" style={{ fontSize: "0.95rem", color: "var(--ink)" }}>
            {complaint.triaged_by}
          </div>
          <div className="meta mono">{complaint.triage_latency_ms} ms</div>
        </div>
      </div>
      {complaint.ai_summary && <p className="receipt__summary">{complaint.ai_summary}</p>}
      {note && <p className="meta">{note}</p>}
    </section>
  );
}
