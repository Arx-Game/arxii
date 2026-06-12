import { describe, expect, it } from 'vitest';
import { formatCoppers } from '../currency';

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
  });
});
