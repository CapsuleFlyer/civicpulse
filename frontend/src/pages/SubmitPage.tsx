import { useState } from "react";
import { ApiError, createComplaint } from "../api/client";
import type { Complaint } from "../api/types";
import TriageReceipt from "../components/TriageReceipt";
import Working from "../components/Working";
import { type DraftErrors, validateDraft } from "../validation";

const EMPTY = { text: "", location: "", reporter_contact: "" };

export default function SubmitPage() {
  const [draft, setDraft] = useState(EMPTY);
  const [errors, setErrors] = useState<DraftErrors>({});
  const [serverError, setServerError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [result, setResult] = useState<Complaint | null>(null);

  async function submit() {
    const found = validateDraft(draft);
    setErrors(found);
    setServerError(null);
    if (Object.keys(found).length > 0) return;

    setSubmitting(true);
    setResult(null);
    try {
      const complaint = await createComplaint({
        text: draft.text.trim(),
        location: draft.location.trim(),
        reporter_contact: draft.reporter_contact.trim() || null,
      });
      setResult(complaint);
      setDraft(EMPTY);
    } catch (error) {
      if (error instanceof ApiError) {
        // The server validated it again and disagreed. Show its reasons, per field.
        setErrors(
          Object.fromEntries(error.fields.map((field) => [field.field, field.message])) as DraftErrors,
        );
        setServerError(error.message);
      } else {
        setServerError("The report could not be sent. Try again in a moment.");
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="page stack">
      <div>
        <h1>Report a problem in your neighbourhood</h1>
        <p className="page__lede">
          Write it the way you would say it. The description is read and sorted automatically, so a
          burst main does not wait behind three streetlight complaints.
        </p>
      </div>

      {serverError && (
        <p className="notice" role="alert">
          {serverError}
        </p>
      )}

      <form
        className="panel"
        noValidate
        onSubmit={(event) => {
          event.preventDefault();
          void submit();
        }}
      >
        <label className="field" data-invalid={Boolean(errors.text)}>
          <span className="field__label">What is happening?</span>
          <span className="field__hint">
            Include when it started and what it is affecting.
          </span>
          <textarea
            name="text"
            value={draft.text}
            aria-invalid={Boolean(errors.text)}
            onChange={(event) => setDraft({ ...draft, text: event.target.value })}
          />
          {errors.text && <span className="field__error">{errors.text}</span>}
        </label>

        <label className="field" data-invalid={Boolean(errors.location)}>
          <span className="field__label">Where is it?</span>
          <span className="field__hint">Street, sector or a landmark nearby.</span>
          <input
            name="location"
            value={draft.location}
            aria-invalid={Boolean(errors.location)}
            onChange={(event) => setDraft({ ...draft, location: event.target.value })}
          />
          {errors.location && <span className="field__error">{errors.location}</span>}
        </label>

        <label className="field" data-invalid={Boolean(errors.reporter_contact)}>
          <span className="field__label">Your phone or email (optional)</span>
          <span className="field__hint">Only used if a crew needs to reach you.</span>
          <input
            name="reporter_contact"
            value={draft.reporter_contact}
            onChange={(event) => setDraft({ ...draft, reporter_contact: event.target.value })}
          />
          {errors.reporter_contact && (
            <span className="field__error">{errors.reporter_contact}</span>
          )}
        </label>

        <button className="button" type="submit" disabled={submitting}>
          {submitting ? "Sending report" : "Send report"}
        </button>

        {submitting && <Working>Reading your report and deciding where it goes…</Working>}
      </form>

      {result && <TriageReceipt complaint={result} />}
    </div>
  );
}
