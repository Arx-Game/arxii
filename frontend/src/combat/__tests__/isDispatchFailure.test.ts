import { describe, expect, it } from 'vitest';
import { isDispatchFailure } from '../types';

describe('isDispatchFailure', () => {
  it('is true only for success === false', () => {
    expect(isDispatchFailure({ success: false })).toBe(true);
    expect(isDispatchFailure({ success: true })).toBe(false);
    expect(isDispatchFailure({ success: null })).toBe(false);
    expect(isDispatchFailure({})).toBe(false);
  });
});
