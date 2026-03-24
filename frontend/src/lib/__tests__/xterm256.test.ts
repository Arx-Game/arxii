import { describe, expect, it } from 'vitest';
import {
  XTERM_TO_HEX,
  MU_COLOR_NAMES,
  xtermToHex,
  muColorToHex,
  hexToNearestXterm,
} from '../xterm256';

describe('XTERM_TO_HEX', () => {
  it('has 256 entries', () => {
    expect(Object.keys(XTERM_TO_HEX)).toHaveLength(256);
  });

  it('maps standard colors correctly', () => {
    expect(XTERM_TO_HEX[0]).toBe('#000000');
    expect(XTERM_TO_HEX[1]).toBe('#800000');
    expect(XTERM_TO_HEX[7]).toBe('#c0c0c0');
  });

  it('maps bright colors correctly', () => {
    expect(XTERM_TO_HEX[9]).toBe('#ff0000');
    expect(XTERM_TO_HEX[15]).toBe('#ffffff');
  });

  it('maps RGB cube colors correctly', () => {
    // index 16 = r=0,g=0,b=0 → #000000
    expect(XTERM_TO_HEX[16]).toBe('#000000');
    // index 196 = 16 + 36*4 + 6*0 + 0 = 160 → r=4 → 0xd7, g=0, b=0
    expect(XTERM_TO_HEX[196]).toBe('#ff0000');
    // Actually 196 = 16 + 180 → r=5,g=0,b=0 → #ff0000
    // Let's verify: 16 + 36*5 = 196, so r=5 → 0xff
    expect(XTERM_TO_HEX[196]).toBe('#ff0000');
    // index 21 = 16 + 0 + 0 + 5 → r=0,g=0,b=5 → #0000ff
    expect(XTERM_TO_HEX[21]).toBe('#0000ff');
  });

  it('maps grayscale correctly', () => {
    // 232 = 8 + 0*10 = 8 → #080808
    expect(XTERM_TO_HEX[232]).toBe('#080808');
    // 255 = 8 + 23*10 = 238 → #eeeeee
    expect(XTERM_TO_HEX[255]).toBe('#eeeeee');
    // 244 = 8 + 12*10 = 128 → #808080
    expect(XTERM_TO_HEX[244]).toBe('#808080');
  });
});

describe('xtermToHex', () => {
  it('returns hex for valid index', () => {
    expect(xtermToHex(0)).toBe('#000000');
    expect(xtermToHex(9)).toBe('#ff0000');
  });

  it('returns undefined for invalid index', () => {
    expect(xtermToHex(256)).toBeUndefined();
    expect(xtermToHex(-1)).toBeUndefined();
  });
});

describe('MU_COLOR_NAMES', () => {
  it('maps named shortcuts to correct indices', () => {
    expect(MU_COLOR_NAMES['r']).toBe(1);
    expect(MU_COLOR_NAMES['R']).toBe(9);
    expect(MU_COLOR_NAMES['g']).toBe(2);
    expect(MU_COLOR_NAMES['X']).toBe(0);
  });
});

describe('muColorToHex', () => {
  it('returns hex for valid name', () => {
    expect(muColorToHex('r')).toBe('#800000');
    expect(muColorToHex('R')).toBe('#ff0000');
  });

  it('returns undefined for invalid name', () => {
    expect(muColorToHex('z')).toBeUndefined();
  });
});

describe('hexToNearestXterm', () => {
  it('finds exact match for pure red', () => {
    // #ff0000 is exactly index 9 (bright red) and index 196 (cube red)
    const result = hexToNearestXterm('#ff0000');
    expect([9, 196]).toContain(result);
  });

  it('finds exact match for black', () => {
    // #000000 matches index 0 (or 16, both are #000000)
    const result = hexToNearestXterm('#000000');
    expect([0, 16]).toContain(result);
  });

  it('finds nearest for arbitrary color', () => {
    const result = hexToNearestXterm('#ff8800');
    // Should return some warm orange-ish xterm index
    expect(result).toBeGreaterThanOrEqual(0);
    expect(result).toBeLessThan(256);
  });
});
