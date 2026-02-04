import { ChevronRight } from 'lucide-react';

interface BreadcrumbItem {
  label: string;
  onClick?: () => void;
}

interface BreadcrumbProps {
  items: BreadcrumbItem[];
}

export function Breadcrumb({ items }: BreadcrumbProps) {
  return (
    <div className="flex items-center gap-1 text-sm text-muted-foreground">
      {items.map((item, index) => (
        <span key={index} className="flex items-center gap-1">
          {index > 0 && <ChevronRight className="h-3 w-3" />}
          {item.onClick ? (
            <button onClick={item.onClick} className="hover:text-foreground hover:underline">
              {item.label}
            </button>
          ) : (
            <span>{item.label}</span>
          )}
        </span>
      ))}
    </div>
  );
}
