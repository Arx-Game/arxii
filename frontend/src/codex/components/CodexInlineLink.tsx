import { cn } from '@/lib/utils';

interface CodexInlineLinkProps {
  entryId: number;
  children: React.ReactNode;
  onNavigate: (entryId: number) => void;
  className?: string;
}

/**
 * Inline clickable link to another codex entry, rendered inside modal content.
 *
 * Calls onNavigate instead of opening a nested modal — the parent modal
 * manages a history stack and swaps content in place.
 *
 * For the full-page EntryDetail view, use React Router <Link> instead.
 */
export function CodexInlineLink({
  entryId,
  children,
  onNavigate,
  className,
}: CodexInlineLinkProps) {
  return (
    <button
      onClick={(e) => {
        e.stopPropagation();
        onNavigate(entryId);
      }}
      className={cn(
        'cursor-pointer text-primary underline decoration-dotted underline-offset-2 hover:decoration-solid',
        className
      )}
    >
      {children}
    </button>
  );
}
