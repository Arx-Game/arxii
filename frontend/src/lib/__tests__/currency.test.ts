import { describe, expect, it } from 'vitest';
import { formatCoppers, parseCoppers } from '../currency';

describe('formatCoppers', () => {
  it('formats zero as 0c', () => {
    expect(formatCoppers(0)).toBe('0c');
  });

  it('formats pure copper', () => {
    expect(formatCoppers(7)).toBe('7c');
  });

  it('formats silver and copper', () => {
    expect(formatCoppers(47)).toBe('4s 7c');
  });

  it('formats the full mixed form', () => {
    expect(formatCoppers(347)).toBe('3g 4s 7c');
  });

  it('omits zero components', () => {
    expect(formatCoppers(300)).toBe('3g');
    expect(formatCoppers(305)).toBe('3g 5c');
    expect(formatCoppers(40)).toBe('4s');
  });

  it('groups large gold amounts', () => {
    expect(formatCoppers(300_000)).toBe('3,000g');
    expect(formatCoppers(1_000_000)).toBe('10,000g');
  });

  it('marks negative amounts', () => {
    expect(formatCoppers(-1_234)).toBe('-12g 3s 4c');
    expect(formatCoppers(-5)).toBe('-5c');
  });

  it('formats exactly one gold', () => {
    expect(formatCoppers(100)).toBe('1g');
  });

  it('does not leave a lone minus on a near-zero fraction', () => {
    expect(formatCoppers(-0.5)).toBe('0c');
  });

  it('degrades non-finite input to 0c', () => {
    expect(formatCoppers(NaN)).toBe('0c');
    expect(formatCoppers(Infinity)).toBe('0c');
    expect(formatCoppers(-Infinity)).toBe('0c');
  });
});

describe('parseCoppers', () => {
  it('parses a single unit', () => {
    expect(parseCoppers('7c')).toBe(7);
    expect(parseCoppers('4s')).toBe(40);
    expect(parseCoppers('3g')).toBe(300);
  });

  it('parses the mixed form regardless of token order', () => {
    expect(parseCoppers('3g 4s 7c')).toBe(347);
    expect(parseCoppers('7c 3g 4s')).toBe(347);
  });

  it('is case-insensitive', () => {
    expect(parseCoppers('3G 4S 7C')).toBe(347);
  });

  it('tolerates extra whitespace between tokens', () => {
    expect(parseCoppers('  3g   4s  7c  ')).toBe(347);
  });

  it('rejects a duplicate unit', () => {
    expect(parseCoppers('1g 2g')).toBeNull();
  });

  it('rejects item-ish text with no unit match', () => {
    expect(parseCoppers('a sword')).toBeNull();
    expect(parseCoppers('50')).toBeNull();
  });

  it('rejects an all-zero total', () => {
    expect(parseCoppers('0c')).toBeNull();
    expect(parseCoppers('0g 0s 0c')).toBeNull();
  });

  it('rejects empty input', () => {
    expect(parseCoppers('')).toBeNull();
    expect(parseCoppers('   ')).toBeNull();
  });

  it('rejects negative amounts (no sign in the grammar)', () => {
    expect(parseCoppers('-3g')).toBeNull();
  });
});
