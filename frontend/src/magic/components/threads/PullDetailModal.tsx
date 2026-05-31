/**
 * PullDetailModal — wraps PullEffectPreview in a Radix Dialog.
 *
 * Triggered by the "▸ details" affordance in ThreadPullPicker rows.
 * The PullEffectPreview handles its own state (tier selection, preview fetch,
 * effects display) — no orchestration needed here.
 */

import { Dialog, DialogContent, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { PullEffectPreview } from './PullEffectPreview';
import type { Thread } from '@/magic/types';

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface PullDetailModalProps {
  thread: Thread;
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

// ---------------------------------------------------------------------------
// PullDetailModal
// ---------------------------------------------------------------------------

export function PullDetailModal({ thread, open, onOpenChange }: PullDetailModalProps) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent
        className="max-w-lg"
        data-testid="pull-detail-modal"
        aria-describedby={undefined}
      >
        <DialogHeader>
          <DialogTitle>{thread.name || `Thread #${thread.id}`}</DialogTitle>
        </DialogHeader>
        <div className="mt-2">
          <PullEffectPreview thread={thread} />
        </div>
      </DialogContent>
    </Dialog>
  );
}
