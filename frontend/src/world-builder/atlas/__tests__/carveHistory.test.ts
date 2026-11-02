import { describe, expect, it } from 'vitest';

import {
  afterHolders,
  beforeHolders,
  chunk,
  EMPTY_HISTORY,
  parseChanged,
  pushEntry,
  restoreRedo,
  restoreUndo,
  takeRedo,
  takeUndo,
  type CarveEntry,
} from '../carveHistory';

const entry: CarveEntry = {
  titleId: 100,
  changed: [
    [1, 2, null, 5],
    [3, 4, 7, 5],
  ],
};
const other: CarveEntry = { titleId: 100, changed: [[9, 9, 5, null]] };

describe('carveHistory', () => {
  it('pushes, undoes onto redo, and redoes back onto undo', () => {
    const pushed = pushEntry(EMPTY_HISTORY, entry);
    expect(pushed.undo).toEqual([entry]);
    expect(pushed.redo).toEqual([]);
    const undone = takeUndo(pushed);
    expect(undone.entry).toBe(entry);
    expect(undone.history).toEqual({ undo: [], redo: [entry] });
    const redone = takeRedo(undone.history);
    expect(redone.entry).toBe(entry);
    expect(redone.history).toEqual({ undo: [entry], redo: [] });
    expect(takeUndo(EMPTY_HISTORY)).toEqual({ history: EMPTY_HISTORY, entry: null });
    expect(takeRedo(EMPTY_HISTORY)).toEqual({ history: EMPTY_HISTORY, entry: null });
  });

  it('clears redo on a new gesture and ignores an empty one', () => {
    const afterUndo = takeUndo(pushEntry(EMPTY_HISTORY, entry)).history;
    const pushed = pushEntry(afterUndo, other);
    expect(pushed).toEqual({ undo: [other], redo: [] });
    expect(pushEntry(pushed, { titleId: 100, changed: [] })).toBe(pushed);
  });

  it('puts an entry back after a refused restore', () => {
    const taken = takeUndo(pushEntry(EMPTY_HISTORY, entry));
    expect(restoreUndo(taken.history, entry)).toEqual({ undo: [entry], redo: [] });
    const redo = takeRedo(taken.history);
    expect(restoreRedo(redo.history, entry)).toEqual({ undo: [], redo: [entry] });
  });

  it('picks the before and after holders', () => {
    expect(beforeHolders(entry)).toEqual([
      [1, 2, null],
      [3, 4, 7],
    ]);
    expect(afterHolders(entry)).toEqual([
      [1, 2, 5],
      [3, 4, 5],
    ]);
  });

  it('chunks a list and reads a dispatch result', () => {
    const items = Array.from({ length: 25 }, (_, i) => i);
    expect(chunk(items, 10).map((c) => c.length)).toEqual([10, 10, 5]);
    expect(chunk([], 10)).toEqual([]);
    expect(parseChanged({ changed: [[1, 2, null, 5]] })).toEqual([[1, 2, null, 5]]);
    expect(parseChanged(null)).toEqual([]);
    expect(parseChanged({ changed: 'nope' })).toEqual([]);
    expect(parseChanged({ changed: [[1, 2]] })).toEqual([]);
  });
});
