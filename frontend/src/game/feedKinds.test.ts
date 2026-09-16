import { describe, expect, it } from 'vitest';
import { FEED_KINDS, classifyInteraction, classifyText } from './feedKinds';

describe('classifyText (#3856)', () => {
  // The server types a text frame through the tuple form's dict, which lands as
  // the frame's kwargs: commands send look/item/error, Evennia's own movement
  // announcements send move (departure) and arrive (arrival), the narrative
  // service sends narrative or gemit. Anything else is a plain line the client
  // cannot place: system.
  it.each([
    ['look', 'look'],
    ['item', 'item'],
    ['error', 'error'],
    ['move', 'move'],
    ['arrive', 'arrive'],
    ['narrative', 'ambience'],
    ['gemit', 'ambience'],
    ['system', 'system'],
    ['weather', 'system'],
    [undefined, 'system'],
    [42, 'system'],
  ])('kwargs.type %s becomes the %s kind', (wireType, expected) => {
    expect(classifyText(wireType)).toBe(expected);
  });

  // A narrative frame carries its category (#3779); only visions get their own lane.
  it('files a narrative frame in the visions category as a vision', () => {
    expect(classifyText('narrative', 'visions')).toBe('vision');
    expect(classifyText('narrative', 'story')).toBe('ambience');
    expect(classifyText('gemit', 'visions')).toBe('ambience');
  });
});

describe('classifyInteraction (#3856)', () => {
  it.each([
    ['pose', 'pose'],
    ['say', 'say'],
    ['emit', 'emit'],
    ['whisper', 'whisper'],
    ['action', 'action'],
  ])('interaction mode %s becomes the %s kind', (mode, expected) => {
    expect(classifyInteraction(mode)).toBe(expected);
  });

  it('treats an unknown mode as a pose, the default the readers already render', () => {
    expect(classifyInteraction('ooc')).toBe('pose');
  });
});

describe('FEED_KINDS', () => {
  it('lists every kind once, so a chip editor can offer them all', () => {
    expect(new Set(FEED_KINDS).size).toBe(FEED_KINDS.length);
    expect(FEED_KINDS).toEqual([
      'pose',
      'say',
      'emit',
      'whisper',
      'action',
      'arrive',
      'move',
      'ambience',
      'vision',
      'look',
      'item',
      'error',
      'system',
    ]);
  });
});
