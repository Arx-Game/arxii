import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import type { Thread } from '../hooks/useThreading';

interface ThreadFilterModalProps {
  open: boolean;
  onClose: () => void;
  thread: Thread;
  hiddenPersonaIds: Set<number>;
  onTogglePersona: (personaId: number) => void;
}

export function ThreadFilterModal({
  open,
  onClose,
  thread,
  hiddenPersonaIds,
  onTogglePersona,
}: ThreadFilterModalProps) {
  const allHidden = thread.participantPersonas.every((p) => hiddenPersonaIds.has(p.id));
  const noneHidden = thread.participantPersonas.every((p) => !hiddenPersonaIds.has(p.id));

  function handleShowAll() {
    for (const p of thread.participantPersonas) {
      if (hiddenPersonaIds.has(p.id)) {
        onTogglePersona(p.id);
      }
    }
  }

  function handleHideAll() {
    for (const p of thread.participantPersonas) {
      if (!hiddenPersonaIds.has(p.id)) {
        onTogglePersona(p.id);
      }
    }
  }

  return (
    <Dialog open={open} onOpenChange={(isOpen) => !isOpen && onClose()}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Filter: {thread.label}</DialogTitle>
          <DialogDescription>
            Show or hide individual participants in this thread.
          </DialogDescription>
        </DialogHeader>

        <div className="flex gap-2">
          <button
            className="rounded border px-2 py-1 text-sm hover:bg-muted disabled:opacity-50"
            onClick={handleShowAll}
            disabled={noneHidden}
          >
            Show All
          </button>
          <button
            className="rounded border px-2 py-1 text-sm hover:bg-muted disabled:opacity-50"
            onClick={handleHideAll}
            disabled={allHidden}
          >
            Hide All
          </button>
        </div>

        <ul className="space-y-2">
          {thread.participantPersonas.map((persona) => {
            const isHidden = hiddenPersonaIds.has(persona.id);
            return (
              <li key={persona.id}>
                <label className="flex cursor-pointer items-center gap-2 text-sm">
                  <input
                    type="checkbox"
                    checked={!isHidden}
                    onChange={() => onTogglePersona(persona.id)}
                    className="h-4 w-4 rounded border-input"
                  />
                  {persona.name}
                </label>
              </li>
            );
          })}
        </ul>
      </DialogContent>
    </Dialog>
  );
}
