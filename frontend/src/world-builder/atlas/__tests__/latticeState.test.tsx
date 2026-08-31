import {
  boundsContaining,
  carveCell,
  cellKey,
  computeFloorRail,
  DEFAULT_BOUNDS,
  emptySketch,
  growBounds,
  growFloor,
  parseCellKey,
  planCell,
  readGrownFloors,
  readLatticeSketch,
  unplanCell,
  writeGrownFloors,
  writeLatticeSketch,
} from '../latticeState';

describe('cellKey / parseCellKey', () => {
  it('round-trips signed coordinates', () => {
    expect(cellKey(-2, 5)).toBe('-2,5');
    expect(parseCellKey(cellKey(-2, 5))).toEqual([-2, 5]);
  });
});

describe('carveCell — the empty -> plan -> void -> restore cycle', () => {
  it('plans an empty cell', () => {
    const sketch = planCell(emptySketch(), cellKey(1, 1));
    expect(sketch.planned).toEqual([cellKey(1, 1)]);
    expect(sketch.voids).toEqual([]);
  });

  it('carving a planned square clears it back to empty (not to a void)', () => {
    const planned = planCell(emptySketch(), cellKey(1, 1));
    const carved = carveCell(planned, cellKey(1, 1));
    expect(carved.planned).toEqual([]);
    expect(carved.voids).toEqual([]);
  });

  it('carving empty ground voids it', () => {
    const carved = carveCell(emptySketch(), cellKey(2, 2));
    expect(carved.voids).toEqual([cellKey(2, 2)]);
    expect(carved.planned).toEqual([]);
  });

  it('carving a void restores it to empty ground', () => {
    const voided = carveCell(emptySketch(), cellKey(2, 2));
    const restored = carveCell(voided, cellKey(2, 2));
    expect(restored.voids).toEqual([]);
    expect(restored.planned).toEqual([]);
  });

  it('completes the full empty -> plan -> clear -> void -> restore cycle', () => {
    const key = cellKey(0, 0);
    let sketch = emptySketch();
    sketch = planCell(sketch, key);
    expect(sketch.planned).toContain(key);
    sketch = carveCell(sketch, key); // plan -> clear
    expect(sketch.planned).not.toContain(key);
    expect(sketch.voids).not.toContain(key);
    sketch = carveCell(sketch, key); // empty -> void
    expect(sketch.voids).toContain(key);
    sketch = carveCell(sketch, key); // void -> restore
    expect(sketch.voids).not.toContain(key);
    expect(sketch.planned).not.toContain(key);
  });

  it('planning is idempotent', () => {
    const key = cellKey(3, 3);
    const once = planCell(emptySketch(), key);
    const twice = planCell(once, key);
    expect(twice.planned).toEqual([key]);
  });

  it('unplanCell removes only the given cell', () => {
    let sketch = planCell(emptySketch(), cellKey(1, 1));
    sketch = planCell(sketch, cellKey(2, 2));
    sketch = unplanCell(sketch, cellKey(1, 1));
    expect(sketch.planned).toEqual([cellKey(2, 2)]);
  });
});

describe('boundsContaining', () => {
  it('widens stored bounds to cover every realized tile', () => {
    const grown = boundsContaining(DEFAULT_BOUNDS, [
      { gridX: -5, gridY: 10 },
      { gridX: 1, gridY: 1 },
    ]);
    expect(grown).toEqual({ minX: -5, maxX: 3, minY: 0, maxY: 10 });
  });

  it('never shrinks ground the viewer already grew', () => {
    const stored = { minX: -2, maxX: 5, minY: -2, maxY: 5 };
    expect(boundsContaining(stored, [{ gridX: 0, gridY: 0 }])).toEqual(stored);
  });
});

describe('growBounds', () => {
  it('north extends the top edge without shifting anything', () => {
    expect(growBounds(DEFAULT_BOUNDS, 'north')).toEqual({ ...DEFAULT_BOUNDS, maxY: 3 });
  });

  it('south extends the bottom edge downward (lower, more negative y)', () => {
    expect(growBounds(DEFAULT_BOUNDS, 'south')).toEqual({ ...DEFAULT_BOUNDS, minY: -1 });
  });

  it('east extends the right edge', () => {
    expect(growBounds(DEFAULT_BOUNDS, 'east')).toEqual({ ...DEFAULT_BOUNDS, maxX: 4 });
  });

  it('west extends the left edge', () => {
    expect(growBounds(DEFAULT_BOUNDS, 'west')).toEqual({ ...DEFAULT_BOUNDS, minX: -1 });
  });
});

describe('floor rail helpers', () => {
  it('always includes ground (0) even with no data and no growth', () => {
    expect(computeFloorRail([], [])).toEqual([0]);
  });

  it('unions data floors and grown floors, highest first', () => {
    expect(computeFloorRail([2, 0], [3, -1])).toEqual([3, 2, 0, -1]);
  });

  it('growFloor("up") adds one above the current highest', () => {
    expect(growFloor([2, 0, -1], 'up')).toBe(3);
  });

  it('growFloor("down") adds one below the current lowest', () => {
    expect(growFloor([2, 0, -1], 'down')).toBe(-2);
  });

  it('growFloor on an empty rail starts at 1 (up) or -1 (down)', () => {
    expect(growFloor([], 'up')).toBe(1);
    expect(growFloor([], 'down')).toBe(-1);
  });
});

describe('localStorage persistence — every access try/catch wrapped', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('round-trips a sketch through read/write', () => {
    const sketch = planCell(carveCell(emptySketch(), cellKey(5, 5)), cellKey(1, 1));
    writeLatticeSketch('acct-1', 'rooms', 42, 0, sketch);
    const read = readLatticeSketch('acct-1', 'rooms', 42, 0);
    expect(read).toEqual(sketch);
  });

  it('keys rooms-mode sketches per floor', () => {
    writeLatticeSketch('acct-1', 'rooms', 42, 0, planCell(emptySketch(), cellKey(9, 9)));
    writeLatticeSketch('acct-1', 'rooms', 42, 1, emptySketch());
    expect(readLatticeSketch('acct-1', 'rooms', 42, 0).planned).toEqual([cellKey(9, 9)]);
    expect(readLatticeSketch('acct-1', 'rooms', 42, 1).planned).toEqual([]);
  });

  it('falls back to an empty sketch when nothing is stored', () => {
    expect(readLatticeSketch('acct-1', 'areas', 7, null)).toEqual(emptySketch());
  });

  it('degrades to an empty sketch instead of throwing when storage is corrupt', () => {
    window.localStorage.setItem('world-builder-lattice:acct-1:areas:7', 'not json');
    expect(readLatticeSketch('acct-1', 'areas', 7, null)).toEqual(emptySketch());
  });

  it('degrades to an empty sketch instead of throwing when localStorage.getItem throws', () => {
    const spy = vi.spyOn(window.localStorage.__proto__, 'getItem').mockImplementation(() => {
      throw new Error('storage disabled');
    });
    expect(readLatticeSketch('acct-1', 'areas', 7, null)).toEqual(emptySketch());
    spy.mockRestore();
  });

  it('degrades silently instead of throwing when localStorage.setItem throws', () => {
    const spy = vi.spyOn(window.localStorage.__proto__, 'setItem').mockImplementation(() => {
      throw new Error('quota exceeded');
    });
    expect(() => writeLatticeSketch('acct-1', 'areas', 7, null, emptySketch())).not.toThrow();
    spy.mockRestore();
  });

  it('round-trips grown floors', () => {
    writeGrownFloors('acct-1', 42, [3, -2]);
    expect(readGrownFloors('acct-1', 42)).toEqual([3, -2]);
  });

  it('falls back to an empty floor list when nothing is stored', () => {
    expect(readGrownFloors('acct-1', 99)).toEqual([]);
  });
});
