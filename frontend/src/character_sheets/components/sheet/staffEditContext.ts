import { createContext, useContext } from 'react';

import type { CharacterSheetStaffEdit } from '@/character_sheets/api';

/** Staff edit mode for the fields below a provider (#3988): null when off. */
export interface StaffEditState {
  sheetId: number;
  stored: CharacterSheetStaffEdit;
}

export const StaffEditContext = createContext<StaffEditState | null>(null);

/** Whether the fields here are being edited, so an empty one keeps a slot. */
export function useStaffEditing(): boolean {
  return useContext(StaffEditContext) !== null;
}
