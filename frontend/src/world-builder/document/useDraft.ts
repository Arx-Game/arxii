/**
 * useDraft (#3477 Task 6) — the manuscript's "draft kept as you type" note,
 * made real: a per-room, per-field localStorage scratchpad so a reload
 * mid-edit never loses typed prose. Keyed `room+field` (never just `field`)
 * so switching rooms in the same session can never bleed one room's draft
 * into another's.
 *
 * Every read/write is try/catch wrapped, matching `useAtlasState`'s
 * localStorage discipline — private browsing, quota, or disabled storage all
 * degrade to "nothing remembered," never a crash. Restore is silent: no
 * "restored from draft" banner, matching the prototype's savebar note
 * ("draft kept as you type") rather than a dedicated indicator.
 */
import { useEffect, useState } from 'react';

function draftKey(roomId: number, field: string): string {
  return `world-builder-draft:${roomId}:${field}`;
}

function readDraft(roomId: number, field: string): string | null {
  try {
    return window.localStorage.getItem(draftKey(roomId, field));
  } catch {
    return null;
  }
}

function writeDraft(roomId: number, field: string, value: string): void {
  try {
    window.localStorage.setItem(draftKey(roomId, field), value);
  } catch {
    // Storage unavailable — the draft is a convenience, never a requirement.
  }
}

function removeDraft(roomId: number, field: string): void {
  try {
    window.localStorage.removeItem(draftKey(roomId, field));
  } catch {
    // Storage unavailable — nothing to clean up.
  }
}

export interface UseDraftResult {
  /** The draft value if one exists, else `remoteValue`. */
  value: string;
  /** Update the draft (and its in-memory value) as the viewer types. */
  setValue: (next: string) => void;
  /** Discard the draft — called after a successful Save carries it to the server. */
  clearDraft: () => void;
}

/**
 * `remoteValue` is the server's current value for this field — used as the
 * starting point whenever no draft exists yet (a fresh room, or one whose
 * draft was already cleared). Switching `roomId` re-reads localStorage for
 * the new room instead of carrying the old room's in-memory value over.
 */
export function useDraft(roomId: number, field: string, remoteValue: string): UseDraftResult {
  const [value, setValueState] = useState<string>(() => readDraft(roomId, field) ?? remoteValue);

  useEffect(() => {
    setValueState(readDraft(roomId, field) ?? remoteValue);
    // Only re-sync when the room/field identity changes — `remoteValue` is
    // intentionally excluded so a server refetch (e.g. another dispatch's
    // cache invalidation) never clobbers text the viewer is mid-typing.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [roomId, field]);

  const setValue = (next: string) => {
    setValueState(next);
    writeDraft(roomId, field, next);
  };

  const clearDraft = () => {
    removeDraft(roomId, field);
  };

  return { value, setValue, clearDraft };
}
