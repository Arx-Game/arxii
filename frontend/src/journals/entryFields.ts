/**
 * What an entry being written consists of (#3941).
 *
 * Its own module rather than a shape hanging off `JournalEntryFields`: both the
 * desk and the composer dialog own one of these in state and hand it to the
 * fields, so neither has to import a component to know what it is holding.
 */
import { isReachActMissing, NO_REACH, type ReachDraft } from '@/magic/reach';
import { isReflectionIncomplete, NO_REFLECTION, type ReflectionDraft } from '@/magic/reflection';
import type { PosthumousOverride } from './api';

/** The subject of a relationship-journal entry, resolved to the sheet the API takes. */
export interface AboutValue {
  /** CharacterSheet id. */
  id: number;
  name: string;
}

export interface JournalEntryFieldsValue {
  isPublic: boolean;
  title: string;
  body: string;
  /**
   * The name as typed. Kept beside the resolved subject rather than inside the
   * fields component because whether it has resolved yet decides whether the
   * entry may be posted, and that is the desk's question, not the field's.
   */
  aboutTerm: string;
  /** The typed name once it is somebody; null while it is not. */
  about: AboutValue | null;
  tags: string[];
  posthumousOverride: PosthumousOverride;
  /** What the entry reflects on (#5124); idle when it reflects on nothing. */
  reflection: ReflectionDraft;
  /** The resonance the entry marks and the act it points at (#5327); idle when it marks nothing. */
  reach: ReachDraft;
}

/**
 * A blank entry. White by default: the white journal is the one people read,
 * and the black one is a deliberate choice, made with the pill right there.
 */
export const EMPTY_ENTRY_FIELDS: JournalEntryFieldsValue = {
  isPublic: true,
  title: '',
  body: '',
  aboutTerm: '',
  about: null,
  tags: [],
  posthumousOverride: 'inherit',
  reflection: NO_REFLECTION,
  reach: NO_REACH,
};

/**
 * A name has been typed into About and it is nobody — either a misspelling, or the
 * type-ahead has not answered yet. Posting now would quietly drop the subject, so the
 * desk and the dialog hold the button until it is one or the other.
 */
export function isAboutUnresolved(value: JournalEntryFieldsValue): boolean {
  return value.aboutTerm.trim() !== '' && value.about === null;
}

/** A target or a choice is set on the reflection row but not both (#5124). */
export function isReflectionUnfinished(value: JournalEntryFieldsValue): boolean {
  return isReflectionIncomplete(value.reflection);
}

/** A resonance is chosen on the entry but no act (#5327): the entry pays only as a mark. */
export function isReachUnfinished(value: JournalEntryFieldsValue): boolean {
  return isReachActMissing(value.reach);
}
