/**
 * Triage calls a language model, which takes seconds. Saying so is more honest
 * than a spinner that implies the page is merely slow.
 */
export default function Working({ children }: { children: React.ReactNode }) {
  return (
    <p className="working" role="status" aria-live="polite">
      <span className="working__dot" aria-hidden="true" />
      {children}
    </p>
  );
}
