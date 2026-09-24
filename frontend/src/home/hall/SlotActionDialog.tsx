/**
 * SlotActionDialog (#3996) — the confirm step for the three slot actions on a
 * character the account holds. Freeze and thaw are for an original character
 * (PLAYER provenance); give up is for a roster character and hands it back to
 * the roster for other players. The dialog states the consequence and runs
 * the mutation; a server refusal is shown as a toast in the server's words.
 *
 * Controlled (`open`/`onOpenChange`) so both the card's overflow menu and the
 * new-character tile can open it without owning a trigger of their own.
 */
import { toast } from 'sonner';

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import {
  useFreezeEntryMutation,
  useGiveUpEntryMutation,
  useThawEntryMutation,
} from '@/roster/queries';
import type { MyRosterEntry } from '@/roster/types';
import { slotActionLabel, type SlotAction } from './slotActions';

const COPY: Record<
  SlotAction,
  { title: (name: string) => string; body: (name: string) => string }
> = {
  freeze: {
    title: (name) => `Freeze ${name}?`,
    body: (name) =>
      `${name} keeps everything and stops using a slot. Thawing is possible after 30 days.`,
  },
  thaw: {
    title: (name) => `Thaw ${name}?`,
    body: (name) => `${name} uses a slot again.`,
  },
  'give-up': {
    title: (name) => `Give up ${name}?`,
    body: (name) =>
      `${name} returns to the roster for other players. Your time with them stays on record.`,
  },
};

interface SlotActionDialogProps {
  entry: MyRosterEntry | null;
  action: SlotAction | null;
  onOpenChange: (open: boolean) => void;
}

export function SlotActionDialog({ entry, action, onOpenChange }: SlotActionDialogProps) {
  const freeze = useFreezeEntryMutation();
  const thaw = useThawEntryMutation();
  const giveUp = useGiveUpEntryMutation();
  const open = entry != null && action != null;
  const mutations = { freeze, thaw, 'give-up': giveUp } as const;
  const mutation = action ? mutations[action] : giveUp;

  function handleConfirm() {
    if (!entry || !action) return;
    mutation.mutate(entry.id, {
      onError: (error: Error) => toast.error(error.message),
    });
    onOpenChange(false);
  }

  const copy = action ? COPY[action] : null;
  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent>
        <AlertDialogHeader>
          <AlertDialogTitle>{entry && copy ? copy.title(entry.name) : ''}</AlertDialogTitle>
          <AlertDialogDescription>
            {entry && copy ? copy.body(entry.name) : ''}
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel>Cancel</AlertDialogCancel>
          <AlertDialogAction onClick={handleConfirm} data-testid="slot-action-confirm">
            {action ? slotActionLabel(action) : ''}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
