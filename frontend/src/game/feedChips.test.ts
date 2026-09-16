import { describe, expect, it } from 'vitest';
import type { FeedNote } from '@/hooks/types';
import type { InteractionWsPayload } from '@/hooks/types';
import {
  DEFAULT_FEED_CHIPS,
  MAX_CUSTOM_CHIPS,
  addCustomChip,
  chipFor,
  deleteChip,
  feedItemKey,
  isKindShown,
  normalizeFeedChips,
  renameChip,
  setChipWake,
  setKindOwner,
  toggleAll,
  toggleChip,
  visibleInteractions,
  visibleNotes,
  wakingKinds,
  type FeedChipState,
} from './feedChips';

const defaults = (): FeedChipState => ({
  chips: DEFAULT_FEED_CHIPS.map((c) => ({ ...c })),
  all: true,
});

describe('default chips (#3856)', () => {
  it('match the demo: Roleplay, Whispers, Movement, Ambience, Visions, System; Roleplay, Whispers and Visions wake', () => {
    expect(DEFAULT_FEED_CHIPS.map((c) => [c.label, c.kinds.join(','), c.wake])).toEqual([
      ['Roleplay', 'pose,say,emit', true],
      ['Whispers', 'whisper', true],
      ['Movement', 'arrive,move', false],
      ['Ambience', 'ambience', false],
      // A vision is rare and prized (#3779): it shows and it wakes.
      ['Visions', 'vision', true],
      ['System', 'look,item,error', false],
    ]);
    expect(DEFAULT_FEED_CHIPS.every((c) => c.on && !c.custom)).toBe(true);
  });

  it('leave system unowned, so it shows unless All is off', () => {
    expect(chipFor('system', DEFAULT_FEED_CHIPS)).toBeNull();
    expect(isKindShown('system', defaults())).toBe(true);
    expect(isKindShown('system', { ...defaults(), all: false })).toBe(false);
  });
});

describe('show rules', () => {
  it('hides a kind when its chip is off and shows it again when on', () => {
    const state = toggleChip(defaults(), 'sy');
    expect(isKindShown('look', state)).toBe(false);
    expect(isKindShown('pose', state)).toBe(true);
    expect(isKindShown('look', toggleChip(state, 'sy'))).toBe(true);
  });

  it('All off hides everything; pressing a chip while All is off turns All on with only that chip', () => {
    const off = toggleAll(defaults());
    expect(off.all).toBe(false);
    expect(isKindShown('pose', off)).toBe(false);
    const only = toggleChip(off, 'rp');
    expect(only.all).toBe(true);
    expect(only.chips.map((c) => [c.id, c.on])).toEqual([
      ['rp', true],
      ['wh', false],
      ['mv', false],
      ['am', false],
      ['vi', false],
      ['sy', false],
    ]);
  });

  it('All on from off turns every chip back on', () => {
    const state = toggleAll(toggleAll(defaults()));
    expect(state.all).toBe(true);
    expect(state.chips.every((c) => c.on)).toBe(true);
  });
});

describe('editing', () => {
  it('moving a kind to another chip removes it from its old owner', () => {
    const state = setKindOwner(defaults(), 'wh', 'say', true);
    expect(chipFor('say', state.chips)?.id).toBe('wh');
    expect(state.chips.find((c) => c.id === 'rp')?.kinds).toEqual(['pose', 'emit']);
  });

  it('unticking a kind leaves it unowned, and an unowned kind still shows', () => {
    const state = setKindOwner(defaults(), 'rp', 'say', false);
    expect(chipFor('say', state.chips)).toBeNull();
    expect(isKindShown('say', state)).toBe(true);
  });

  it('adds up to three custom chips, each on, not waking, with an empty kind list', () => {
    let state = defaults();
    for (let n = 1; n <= MAX_CUSTOM_CHIPS + 1; n += 1) state = addCustomChip(state);
    const custom = state.chips.filter((c) => c.custom);
    expect(custom).toHaveLength(MAX_CUSTOM_CHIPS);
    expect(custom.map((c) => c.label)).toEqual(['Chip 1', 'Chip 2', 'Chip 3']);
    expect(custom.every((c) => c.on && !c.wake && c.kinds.length === 0)).toBe(true);
  });

  it('deleting a chip leaves its kinds unowned, and a default chip may be deleted too', () => {
    const state = deleteChip(defaults(), 'sy');
    expect(state.chips.map((c) => c.id)).toEqual(['rp', 'wh', 'mv', 'am', 'vi']);
    expect(isKindShown('look', state)).toBe(true);
  });

  it('renames within the label limit and refuses a blank name', () => {
    expect(renameChip(defaults(), 'rp', '  Story ').chips[0].label).toBe('Story');
    expect(renameChip(defaults(), 'rp', '   ').chips[0].label).toBe('Roleplay');
    expect(renameChip(defaults(), 'rp', 'x'.repeat(40)).chips[0].label).toHaveLength(18);
  });

  it('wake is per chip', () => {
    const state = setChipWake(defaults(), 'am', true);
    expect(wakingKinds(state.chips)).toEqual(
      new Set(['pose', 'say', 'emit', 'whisper', 'ambience', 'vision'])
    );
    expect(wakingKinds(toggleChip(state, 'rp').chips)).toEqual(
      new Set(['whisper', 'ambience', 'vision'])
    );
  });
});

describe('normalizeFeedChips', () => {
  it('returns the defaults for anything that is not a chip list', () => {
    expect(normalizeFeedChips(undefined)).toEqual(DEFAULT_FEED_CHIPS);
    expect(normalizeFeedChips('nope')).toEqual(DEFAULT_FEED_CHIPS);
    expect(normalizeFeedChips([])).toEqual(DEFAULT_FEED_CHIPS);
  });

  it('drops unknown kinds, duplicate ownership, and custom chips past the cap', () => {
    const chips = normalizeFeedChips([
      { id: 'a', label: 'A', kinds: ['pose', 'bogus', 'say'], on: true, wake: 1, custom: false },
      { id: 'b', label: '', kinds: ['say'], on: 'yes', wake: false, custom: true },
      { id: 'c', label: 'C', kinds: [], on: true, wake: false, custom: true },
      { id: 'd', label: 'D', kinds: [], on: true, wake: false, custom: true },
      { id: 'e', label: 'E', kinds: [], on: true, wake: false, custom: true },
    ]);
    expect(chips.map((c) => [c.id, c.label, c.kinds, c.on, c.wake, c.custom])).toEqual([
      ['a', 'A', ['pose', 'say'], true, true, false],
      ['b', 'Chip', [], true, false, true],
      ['c', 'C', [], true, false, true],
      ['d', 'D', [], true, false, true],
    ]);
  });
});

const note = (id: string, kind: FeedNote['kind']): FeedNote => ({
  id,
  kind,
  content: id,
  timestamp: '2026-09-14T22:00:00.000Z',
});

const interaction = (id: number, mode: string): InteractionWsPayload => ({
  id,
  persona: { id: 1, name: 'Nyx', thumbnail_url: '' },
  content: String(id),
  mode,
  timestamp: '2026-09-14T22:00:00Z',
  scene_id: 1,
  place_id: null,
  place_name: null,
  receiver_persona_ids: [],
  target_persona_ids: [],
});

describe('visible items', () => {
  it('filters notes by their kind, interactions by their mode, and drops dismissed ones', () => {
    const state = toggleChip(defaults(), 'sy');
    const dismissed = new Set([feedItemKey('note', 'n2'), feedItemKey('interaction', 2)]);
    expect(
      visibleNotes(
        [note('n1', 'look'), note('n2', 'arrive'), note('n3', 'move'), note('n4', 'system')],
        state,
        dismissed
      ).map((n) => n.id)
    ).toEqual(['n3', 'n4']);
    expect(
      visibleInteractions(
        [interaction(1, 'pose'), interaction(2, 'pose'), interaction(3, 'whisper')],
        toggleChip(state, 'wh'),
        dismissed
      ).map((i) => i.id)
    ).toEqual([1]);
  });

  it('returns the same array when nothing is filtered, so memoised consumers keep their identity', () => {
    const items = [interaction(1, 'pose')];
    expect(visibleInteractions(items, defaults(), new Set())).toBe(items);
  });
});
