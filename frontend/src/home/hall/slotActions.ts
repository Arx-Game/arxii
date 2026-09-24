/**
 * Slot action vocabulary (#3996), shared by the card menu, the new-character
 * tile and the confirm dialog. Original characters (PLAYER provenance) freeze
 * and thaw; roster characters are given up.
 */
import type { MyRosterEntry } from '@/roster/types';

export type SlotAction = 'freeze' | 'thaw' | 'give-up';

export function slotActionFor(entry: MyRosterEntry): SlotAction {
  if (entry.creation_provenance !== 'PLAYER') return 'give-up';
  return entry.activity_state === 'FROZEN' ? 'thaw' : 'freeze';
}

const LABELS: Record<SlotAction, string> = {
  freeze: 'Freeze',
  thaw: 'Thaw',
  'give-up': 'Give up',
};

export function slotActionLabel(action: SlotAction): string {
  return LABELS[action];
}
