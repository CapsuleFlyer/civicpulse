const LABELS: Record<string, string> = {
  in_progress: "In progress",
  open: "Open",
  resolved: "Resolved",
  rejected: "Rejected",
  high: "High",
  normal: "Normal",
  low: "Low",
};

export function label(value: string): string {
  return LABELS[value] ?? value.charAt(0).toUpperCase() + value.slice(1);
}

/**
 * A tag renders a value the server decided. The component knows how to spell a
 * status, never which statuses are legal — that table lives in the backend.
 */
export default function Tag({ value, title }: { value: string; title?: string }) {
  return (
    <span className={`tag tag--${value}`} title={title}>
      {label(value)}
    </span>
  );
}
