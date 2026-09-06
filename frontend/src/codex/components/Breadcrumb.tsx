import { ChevronRight } from 'lucide-react';

interface BreadcrumbItem {
  label: string;
  onClick?: () => void;
}

interface BreadcrumbProps {
  items: BreadcrumbItem[];
}

/**
 * A single breadcrumb segment: a clickable link when `onClick` is given, plain
 * text otherwise. Exported so callers that need one breadcrumb-styled link
 * outside a full trail (e.g. the "Also filed under" line on an entry) reuse
 * the same styling instead of hand-rolling a button.
 */
export function BreadcrumbLink({ label, onClick }: BreadcrumbItem) {
  return onClick ? (
    <button onClick={onClick} className="hover:text-foreground hover:underline">
      {label}
    </button>
  ) : (
    <span>{label}</span>
  );
}

export function Breadcrumb({ items }: BreadcrumbProps) {
  return (
    <div className="flex items-center gap-1 text-sm text-muted-foreground">
      {items.map((item, index) => (
        <span key={item.label} className="flex items-center gap-1">
          {index > 0 && <ChevronRight className="h-3 w-3" />}
          <BreadcrumbLink label={item.label} onClick={item.onClick} />
        </span>
      ))}
    </div>
  );
}
