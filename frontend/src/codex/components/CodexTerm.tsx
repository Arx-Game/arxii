import { useState, ReactNode } from 'react';
import { CodexModal } from './CodexModal';
import { cn } from '@/lib/utils';

interface CodexTermProps {
  entryId: number;
  children: ReactNode;
  className?: string;
}

export function CodexTerm({ entryId, children, className }: CodexTermProps) {
  const [open, setOpen] = useState(false);

  return (
    <>
      <button
        onClick={(e) => {
          e.stopPropagation();
          setOpen(true);
        }}
        className={cn(
          'cursor-pointer text-primary underline decoration-dotted underline-offset-2 hover:decoration-solid',
          className
        )}
      >
        {children}
      </button>
      <CodexModal entryId={entryId} open={open} onOpenChange={setOpen} />
    </>
  );
}
