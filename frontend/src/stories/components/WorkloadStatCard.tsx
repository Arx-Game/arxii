/**
 * WorkloadStatCard — single top-line count card for the Staff Workload page.
 * Shows a large number, a label below, and an optional sublabel.
 */

interface WorkloadStatCardProps {
  label: string;
  value: number;
  sublabel?: string;
  /** Optional accent class applied to the number for semantic colour. */
  valueClassName?: string;
}

export function WorkloadStatCard({
  label,
  value,
  sublabel,
  valueClassName = '',
}: WorkloadStatCardProps) {
  return (
    <div className="flex flex-col items-center justify-center rounded-lg border bg-card p-6 text-center shadow-sm">
      <span className={`text-4xl font-bold tabular-nums ${valueClassName}`}>{value}</span>
      <span className="mt-2 text-sm font-medium text-foreground">{label}</span>
      {sublabel && <span className="mt-1 text-xs text-muted-foreground">{sublabel}</span>}
    </div>
  );
}
