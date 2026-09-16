import type { FeedNote, InteractionWsPayload } from '@/hooks/types';
import { FEED_KINDS, classifyInteraction, type FeedKind } from './feedKinds';

/**
 * The filter chips above the feed (#3856, PR 2). A chip owns a set of kinds; a
 * kind belongs to at most one chip. Pressing a chip shows or hides its kinds;
 * All is the master switch. A kind no chip owns still shows unless All is
 * off (Dan's ruling: deleting a chip can never lose a kind). Show and wake
 * are separate per chip: ambience shows and never wakes by default.
 *
 * Everything here is pure; the strip and editor components call these and
 * write the result to `PlayPreferences`.
 */
export interface FeedChip {
  id: string;
  label: string;
  kinds: FeedKind[];
  on: boolean;
  wake: boolean;
  custom: boolean;
}

export interface FeedChipState {
  chips: FeedChip[];
  all: boolean;
}

export const MAX_CUSTOM_CHIPS = 3;
export const MAX_CHIP_LABEL = 18;

export const DEFAULT_FEED_CHIPS: readonly FeedChip[] = [
  {
    id: 'rp',
    label: 'Roleplay',
    kinds: ['pose', 'say', 'emit'],
    on: true,
    wake: true,
    custom: false,
  },
  { id: 'wh', label: 'Whispers', kinds: ['whisper'], on: true, wake: true, custom: false },
  { id: 'mv', label: 'Movement', kinds: ['arrive', 'move'], on: true, wake: false, custom: false },
  { id: 'am', label: 'Ambience', kinds: ['ambience'], on: true, wake: false, custom: false },
  // A vision is rare and prized (#3779): it shows and it wakes.
  { id: 'vi', label: 'Visions', kinds: ['vision'], on: true, wake: true, custom: false },
  {
    id: 'sy',
    label: 'System',
    kinds: ['look', 'item', 'error'],
    on: true,
    wake: false,
    custom: false,
  },
];

/** The editor's label for each kind, in the order it lists them. */
export const KIND_LABELS: Record<FeedKind, string> = {
  pose: 'Poses',
  say: 'Speech',
  emit: 'GM emits',
  whisper: 'Whispers',
  action: 'Actions and outcomes',
  arrive: 'Arrivals and departures',
  move: 'Your own movement',
  ambience: 'Ambient flavour',
  vision: 'Visions',
  look: 'Look results',
  item: 'Item handling',
  error: 'Command errors',
  system: 'Everything else',
};

export function chipFor(kind: FeedKind, chips: readonly FeedChip[]): FeedChip | null {
  return chips.find((chip) => chip.kinds.includes(kind)) ?? null;
}

export function isKindShown(kind: FeedKind, state: FeedChipState): boolean {
  if (!state.all) return false;
  const chip = chipFor(kind, state.chips);
  return chip ? chip.on : true;
}

/** Kinds whose arrival should wake the player: owned by a chip that is on and set to wake. */
export function wakingKinds(chips: readonly FeedChip[]): Set<FeedKind> {
  const kinds = new Set<FeedKind>();
  for (const chip of chips) {
    if (chip.on && chip.wake) for (const kind of chip.kinds) kinds.add(kind);
  }
  return kinds;
}

function replaceChip(
  state: FeedChipState,
  id: string,
  patch: (chip: FeedChip) => FeedChip
): FeedChipState {
  return { ...state, chips: state.chips.map((chip) => (chip.id === id ? patch(chip) : chip)) };
}

/**
 * Press a chip. With All on, the chip toggles. With All off the column is empty,
 * so a press means "show me this one": All comes back on with only that chip.
 */
export function toggleChip(state: FeedChipState, id: string): FeedChipState {
  if (!state.all) {
    return { all: true, chips: state.chips.map((chip) => ({ ...chip, on: chip.id === id })) };
  }
  return replaceChip(state, id, (chip) => ({ ...chip, on: !chip.on }));
}

/** The master switch. Turning All back on turns every chip on with it. */
export function toggleAll(state: FeedChipState): FeedChipState {
  if (state.all) return { ...state, all: false };
  return { all: true, chips: state.chips.map((chip) => ({ ...chip, on: true })) };
}

/** Give a kind to a chip (taking it from its old owner), or take it away and leave it unowned. */
export function setKindOwner(
  state: FeedChipState,
  chipId: string,
  kind: FeedKind,
  owned: boolean
): FeedChipState {
  return {
    ...state,
    chips: state.chips.map((chip) => {
      const without = chip.kinds.filter((k) => k !== kind);
      if (chip.id !== chipId)
        return without.length === chip.kinds.length ? chip : { ...chip, kinds: without };
      return { ...chip, kinds: owned ? [...without, kind] : without };
    }),
  };
}

export function renameChip(state: FeedChipState, id: string, label: string): FeedChipState {
  const trimmed = label.trim().slice(0, MAX_CHIP_LABEL);
  if (!trimmed) return state;
  return replaceChip(state, id, (chip) => ({ ...chip, label: trimmed }));
}

export function setChipWake(state: FeedChipState, id: string, wake: boolean): FeedChipState {
  return replaceChip(state, id, (chip) => ({ ...chip, wake }));
}

/** Add a custom chip, on and silent, with no kinds yet; nothing past the cap. Returns the new chip's id on `newChipId`. */
export function addCustomChip(state: FeedChipState): FeedChipState & { newChipId?: string } {
  const custom = state.chips.filter((chip) => chip.custom);
  if (custom.length >= MAX_CUSTOM_CHIPS) return state;
  const taken = new Set(state.chips.map((chip) => chip.id));
  let n = custom.length + 1;
  while (taken.has(`c${n}`)) n += 1;
  const chip: FeedChip = {
    id: `c${n}`,
    label: `Chip ${custom.length + 1}`,
    kinds: [],
    on: true,
    wake: false,
    custom: true,
  };
  return { ...state, chips: [...state.chips, chip], newChipId: chip.id };
}

/** Remove any chip. Its kinds become unowned and keep showing. */
export function deleteChip(state: FeedChipState, id: string): FeedChipState {
  return { ...state, chips: state.chips.filter((chip) => chip.id !== id) };
}

const KIND_SET = new Set<string>(FEED_KINDS);

/**
 * Rebuild a stored chip list into a valid one: only known kinds, each owned
 * once (first chip wins), booleans coerced, labels clamped, at most three
 * custom chips. Anything that is not a non-empty list yields the defaults.
 */
export function normalizeFeedChips(value: unknown): FeedChip[] {
  if (!Array.isArray(value) || value.length === 0) return DEFAULT_FEED_CHIPS.map((c) => ({ ...c }));
  const seenIds = new Set<string>();
  const seenKinds = new Set<FeedKind>();
  const chips: FeedChip[] = [];
  let customCount = 0;
  for (const raw of value) {
    if (!raw || typeof raw !== 'object') continue;
    const record = raw as Record<string, unknown>;
    const id = typeof record.id === 'string' ? record.id : '';
    if (!id || seenIds.has(id)) continue;
    const custom = Boolean(record.custom);
    if (custom && customCount >= MAX_CUSTOM_CHIPS) continue;
    const kinds: FeedKind[] = [];
    for (const kind of Array.isArray(record.kinds) ? record.kinds : []) {
      if (typeof kind === 'string' && KIND_SET.has(kind) && !seenKinds.has(kind as FeedKind)) {
        kinds.push(kind as FeedKind);
        seenKinds.add(kind as FeedKind);
      }
    }
    const label =
      (typeof record.label === 'string' ? record.label.trim().slice(0, MAX_CHIP_LABEL) : '') ||
      'Chip';
    chips.push({ id, label, kinds, on: Boolean(record.on), wake: Boolean(record.wake), custom });
    seenIds.add(id);
    if (custom) customCount += 1;
  }
  return chips.length ? chips : DEFAULT_FEED_CHIPS.map((c) => ({ ...c }));
}

/** The key minimise and dismiss are recorded under, per viewer. */
export function feedItemKey(type: 'interaction' | 'note', id: number | string): string {
  return type === 'interaction' ? `i:${id}` : `n:${id}`;
}

/** Interactions the chips let through, minus dismissed ones. The same array back when nothing is filtered. */
export function visibleInteractions<T extends Pick<InteractionWsPayload, 'id' | 'mode'>>(
  items: T[],
  state: FeedChipState,
  dismissed: ReadonlySet<string>
): T[] {
  const kept = items.filter(
    (item) =>
      isKindShown(classifyInteraction(item.mode), state) &&
      !dismissed.has(feedItemKey('interaction', item.id))
  );
  return kept.length === items.length ? items : kept;
}

export function visibleNotes(
  notes: FeedNote[],
  state: FeedChipState,
  dismissed: ReadonlySet<string>
): FeedNote[] {
  const kept = notes.filter(
    (note) => isKindShown(note.kind, state) && !dismissed.has(feedItemKey('note', note.id))
  );
  return kept.length === notes.length ? notes : kept;
}
