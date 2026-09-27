import { useEffect } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { GripVertical } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { PersonaAvatar } from '@/components/PersonaAvatar';
import { FormattedContent } from '@/components/FormattedContent';
import { cn } from '@/lib/utils';

import { useDraggable } from './useDraggable';

export interface LookDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  personaName: string;
  thumbnailUrl?: string | null;
  text: string;
  isLoading: boolean;
  onViewSheet: () => void;
}

/**
 * A draggable, overlay-less "Look" dialog (#4030 demo Screen 2). Built directly on
 * @radix-ui/react-dialog rather than components/ui/dialog.tsx's `DialogContent`,
 * which always renders the black overlay — this panel floats over the play column
 * without dimming it, so the reader stays readable while the dialog is open.
 */
export function LookDialog({
  open,
  onOpenChange,
  personaName,
  thumbnailUrl,
  text,
  isLoading,
  onViewSheet,
}: LookDialogProps) {
  const { offset, handleProps, reset } = useDraggable();

  useEffect(() => {
    if (!open) {
      reset();
    }
    // reset() is intentionally excluded: it is a fresh function each render, and
    // including it would re-run this effect (and reset the offset) every render
    // while the dialog is closed.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);

  return (
    <Dialog.Root open={open} onOpenChange={onOpenChange} modal={false}>
      <Dialog.Portal>
        <Dialog.Content
          aria-describedby={undefined}
          className={cn(
            'fixed left-1/2 top-24 z-50 w-[min(28rem,calc(100vw-2rem))] -translate-x-1/2',
            'max-h-[70vh] overflow-y-auto rounded-lg border bg-background shadow-lg'
          )}
          style={{
            transform: `translate(calc(-50% + ${offset.x}px), ${offset.y}px)`,
          }}
        >
          <div
            data-testid="look-dialog-handle"
            className="flex cursor-move items-center gap-2 border-b px-3 py-2"
            onPointerDown={handleProps.onPointerDown}
          >
            <GripVertical className="size-4 shrink-0 text-muted-foreground" />
            <PersonaAvatar source={{ name: personaName, thumbnailUrl }} size="sm" />
            <Dialog.Title className="flex-1 truncate text-sm font-semibold">
              {personaName}
            </Dialog.Title>
            <Dialog.Close
              aria-label="Close"
              className="rounded-sm opacity-70 ring-offset-background transition-opacity hover:opacity-100 focus:outline-none focus:ring-2 focus:ring-ring focus:ring-offset-2"
            >
              &times;
            </Dialog.Close>
          </div>
          <div className="px-3 py-3 text-sm">
            {isLoading ? 'Looking…' : <FormattedContent content={text} />}
          </div>
          <div className="flex justify-end border-t px-3 py-2">
            <Button variant="outline" size="sm" onClick={onViewSheet}>
              View sheet
            </Button>
          </div>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
}
