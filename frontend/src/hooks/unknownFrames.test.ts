import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import {
  recordUnknownFrame,
  recordedUnknownFrames,
  __resetUnknownFramesForTests,
} from './unknownFrames';

describe('unknownFrames (#3933)', () => {
  beforeEach(() => {
    __resetUnknownFramesForTests();
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-09-19T12:00:00.000Z'));
    vi.spyOn(console, 'warn').mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it('records type, generation and an ISO timestamp', () => {
    recordUnknownFrame('mystery', 3);

    expect(recordedUnknownFrames()).toEqual([
      { type: 'mystery', generation: 3, at: '2026-09-19T12:00:00.000Z' },
    ]);
  });

  it('caps at 50 keeping the newest', () => {
    for (let i = 0; i < 55; i += 1) {
      recordUnknownFrame(`frame-${i}`, 1);
    }

    const frames = recordedUnknownFrames();
    expect(frames).toHaveLength(50);
    expect(frames[0].type).toBe('frame-5');
    expect(frames[frames.length - 1].type).toBe('frame-54');
  });

  it('__resetUnknownFramesForTests clears', () => {
    recordUnknownFrame('mystery', 1);
    __resetUnknownFramesForTests();

    expect(recordedUnknownFrames()).toEqual([]);
  });
});
