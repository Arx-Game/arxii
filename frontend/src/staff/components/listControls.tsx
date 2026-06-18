import { Button } from '@/components/ui/button';

interface StatusFilterOption<T> {
  label: string;
  value: T;
}

interface StatusFilterBarProps<T> {
  options: StatusFilterOption<T>[];
  value: T;
  onChange: (value: T) => void;
}

/** The status-filter button row shared by every staff list page. */
export function StatusFilterBar<T>({ options, value, onChange }: StatusFilterBarProps<T>) {
  return (
    <div className="mb-6 flex flex-wrap gap-2">
      {options.map((opt) => (
        <Button
          key={opt.label}
          variant={value === opt.value ? 'default' : 'outline'}
          size="sm"
          onClick={() => onChange(opt.value)}
        >
          {opt.label}
        </Button>
      ))}
    </div>
  );
}

interface NextPrevPaginationProps {
  page: number;
  hasPrevious: boolean;
  hasNext: boolean;
  onPageChange: (page: number) => void;
}

/** The next/previous pagination footer shared by every staff list page.
 *  Renders nothing when there is neither a previous nor a next page. */
export function NextPrevPagination({
  page,
  hasPrevious,
  hasNext,
  onPageChange,
}: NextPrevPaginationProps) {
  if (!hasPrevious && !hasNext) return null;
  return (
    <div className="mt-6 flex items-center justify-center gap-4">
      <Button
        variant="outline"
        size="sm"
        disabled={!hasPrevious}
        onClick={() => onPageChange(page - 1)}
      >
        Previous
      </Button>
      <span className="text-sm text-muted-foreground">Page {page}</span>
      <Button
        variant="outline"
        size="sm"
        disabled={!hasNext}
        onClick={() => onPageChange(page + 1)}
      >
        Next
      </Button>
    </div>
  );
}
