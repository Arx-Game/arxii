/**
 * The carve page's undo and redo (#4905), as pure stack arithmetic. An entry is what
 * one gesture changed, per pip: holder before and holder after. Undo restores the
 * before column, redo the after column, through `atlas_restore_footprint`; neither
 * reverses the carve by inverting it, since shrinking hands a pip to the ladder
 * parent rather than to whoever held it (ADR-4905).
 */

/** One pip a carve or clear touched: x, y, holder area before, holder area after. */
export type PipChange = [number, number, number | null, number | null];
/** A pip and the holder to give it; null is open ground. */
export type PipHolder = [number, number, number | null];

export interface CarveEntry {
  titleId: number;
  changed: PipChange[];
}

export interface CarveHistory {
  undo: CarveEntry[];
  redo: CarveEntry[];
}

export const EMPTY_HISTORY: CarveHistory = { undo: [], redo: [] };

/** A new gesture: onto the undo stack, and nothing is left to redo. */
export function pushEntry(history: CarveHistory, entry: CarveEntry): CarveHistory {
  if (entry.changed.length === 0) return history;
  return { undo: [...history.undo, entry], redo: [] };
}

export function takeUndo(history: CarveHistory): {
  history: CarveHistory;
  entry: CarveEntry | null;
} {
  const entry = history.undo.at(-1) ?? null;
  if (entry == null) return { history, entry: null };
  return {
    history: { undo: history.undo.slice(0, -1), redo: [...history.redo, entry] },
    entry,
  };
}

export function takeRedo(history: CarveHistory): {
  history: CarveHistory;
  entry: CarveEntry | null;
} {
  const entry = history.redo.at(-1) ?? null;
  if (entry == null) return { history, entry: null };
  return {
    history: { undo: [...history.undo, entry], redo: history.redo.slice(0, -1) },
    entry,
  };
}

/** The server refused the undo's restore: the entry goes back where it was. */
export function restoreUndo(history: CarveHistory, entry: CarveEntry): CarveHistory {
  return { undo: [...history.undo, entry], redo: history.redo.filter((e) => e !== entry) };
}

/** The server refused the redo's restore: the entry goes back where it was. */
export function restoreRedo(history: CarveHistory, entry: CarveEntry): CarveHistory {
  return { undo: history.undo.filter((e) => e !== entry), redo: [...history.redo, entry] };
}

export function beforeHolders(entry: CarveEntry): PipHolder[] {
  return entry.changed.map(([x, y, before]) => [x, y, before]);
}

export function afterHolders(entry: CarveEntry): PipHolder[] {
  return entry.changed.map(([x, y, , after]) => [x, y, after]);
}

export function chunk<T>(items: T[], size: number): T[][] {
  const out: T[][] = [];
  for (let i = 0; i < items.length; i += size) out.push(items.slice(i, i + size));
  return out;
}

function isHolder(value: unknown): value is number | null {
  return value === null || typeof value === 'number';
}

/** `data.changed` from a carve or clear dispatch result; `[]` when absent or malformed. */
export function parseChanged(data: unknown): PipChange[] {
  if (data == null || typeof data !== 'object') return [];
  const changed = (data as { changed?: unknown }).changed;
  if (!Array.isArray(changed)) return [];
  const out: PipChange[] = [];
  for (const item of changed) {
    if (
      !Array.isArray(item) ||
      item.length !== 4 ||
      typeof item[0] !== 'number' ||
      typeof item[1] !== 'number' ||
      !isHolder(item[2]) ||
      !isHolder(item[3])
    ) {
      return [];
    }
    out.push([item[0], item[1], item[2], item[3]]);
  }
  return out;
}
