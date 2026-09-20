/**
 * What an entry being written consists of (#3941).
 *
 * Its own module rather than a shape hanging off `JournalEntryFields`: both the
 * desk and the composer dialog own one of these in state and hand it to the
 * fields, so neither has to import a component to know what it is holding.
 */
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
  about: AboutValue | null;
  tags: string[];
  posthumousOverride: PosthumousOverride;
}

/**
 * A blank entry. White by default: the white journal is the one people read,
 * and the black one is a deliberate choice, made with the pill right there.
 */
export const EMPTY_ENTRY_FIELDS: JournalEntryFieldsValue = {
  isPublic: true,
  title: '',
  body: '',
  about: null,
  tags: [],
  posthumousOverride: 'inherit',
};
