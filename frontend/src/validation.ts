/**
 * Client-side validation mirrors the server's rules to give fast feedback. It
 * does not replace them: the server validates every field again, and a 400
 * response is rendered field by field. The constants live here in one place so
 * a change is a one-line change, not a hunt.
 */
export const LIMITS = {
  text: { min: 10, max: 2000 },
  location: { min: 3, max: 200 },
  contact: { max: 120 },
} as const;

export type DraftErrors = Partial<Record<"text" | "location" | "reporter_contact", string>>;

export function validateDraft(draft: {
  text: string;
  location: string;
  reporter_contact: string;
}): DraftErrors {
  const errors: DraftErrors = {};
  const text = draft.text.trim();
  const location = draft.location.trim();

  if (text.length < LIMITS.text.min) {
    errors.text = `Describe the problem in at least ${LIMITS.text.min} characters so it can be triaged.`;
  } else if (text.length > LIMITS.text.max) {
    errors.text = `Keep the description under ${LIMITS.text.max} characters.`;
  }

  if (location.length < LIMITS.location.min) {
    errors.location = "Add a street, sector or landmark so a crew can find it.";
  } else if (location.length > LIMITS.location.max) {
    errors.location = `Keep the location under ${LIMITS.location.max} characters.`;
  }

  if (draft.reporter_contact.trim().length > LIMITS.contact.max) {
    errors.reporter_contact = `Keep the contact under ${LIMITS.contact.max} characters.`;
  }

  return errors;
}
