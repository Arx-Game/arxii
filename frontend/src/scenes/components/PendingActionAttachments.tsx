import { Paperclip, X, RotateCcw } from 'lucide-react';
import { cn } from '@/lib/utils';
import { usePendingUnlinkedActions } from '../hooks/usePendingUnlinkedActions';

interface PendingActionAttachmentsProps {
  sceneId: string;
  personaId: number | null;
  detachedIds: number[];
  onDetach: (id: number) => void;
  onUndoDetach: (id: number) => void;
}

/** Truncate action content to a short summary for chip display. */
function terseSummary(content: string, maxLength: number = 60): string {
  const stripped = content.replace(/<[^>]*>/g, '').trim();
  if (stripped.length <= maxLength) return stripped;
  return stripped.slice(0, maxLength - 1) + '…';
}

export function PendingActionAttachments({
  sceneId,
  personaId,
  detachedIds,
  onDetach,
  onUndoDetach,
}: PendingActionAttachmentsProps) {
  const { data: actions } = usePendingUnlinkedActions(sceneId, personaId);

  // If there are no pending unlinked actions at all, render nothing.
  if (actions.length === 0) {
    return null;
  }

  const detachedSet = new Set(detachedIds);

  return (
    <div className="flex flex-wrap gap-1 px-3 py-1.5">
      {actions.map((action) => {
        const isDetached = detachedSet.has(action.id);
        const summary = terseSummary(action.content);

        if (isDetached) {
          return (
            <span
              key={action.id}
              className={cn(
                'flex items-center gap-1 rounded border border-border bg-muted/60 px-2 py-0.5 text-xs text-muted-foreground'
              )}
            >
              <Paperclip className="h-3 w-3 shrink-0 opacity-50" />
              <span className="line-through">{summary}</span>
              <button
                type="button"
                aria-label={`Undo detach: ${summary}`}
                onClick={() => onUndoDetach(action.id)}
                className="ml-0.5 flex items-center gap-0.5 rounded px-0.5 hover:bg-accent hover:text-accent-foreground"
              >
                <RotateCcw className="h-3 w-3" />
                <span>undo</span>
              </button>
            </span>
          );
        }

        return (
          <span
            key={action.id}
            className={cn(
              'flex items-center gap-1 rounded border border-border bg-muted/60 px-2 py-0.5 text-xs text-foreground'
            )}
          >
            <Paperclip className="h-3 w-3 shrink-0" />
            <span>Attaching: {summary}</span>
            <button
              type="button"
              aria-label={`Detach action: ${summary}`}
              onClick={() => onDetach(action.id)}
              className="ml-0.5 rounded p-0.5 hover:bg-accent hover:text-accent-foreground"
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        );
      })}
    </div>
  );
}
