import { createContext, createElement, useContext, type ReactNode } from 'react';
import type { FeedNote } from '@/hooks/types';

/** What a line needs for a find: its text as shown, its recorded text, its speaker. */
export interface FindableLine {
  content: string;
  line?: string | null;
  persona?: { name: string };
}

/**
 * Find in this session (#4129): the find box at the rail's foot narrows what
 * the session holds to lines containing the text, within the current rail
 * selection and chips. Everything here is pure except the context, which
 * carries the needle to the line renderers so matches are marked where the
 * text is drawn, without threading a prop through every reader.
 */

/** A needle as typed, trimmed; empty means no find is active. */
export function normalizeFind(text: string): string {
  return text.trim();
}

function contains(haystack: string | null | undefined, needle: string): boolean {
  return Boolean(haystack) && (haystack as string).toLowerCase().includes(needle.toLowerCase());
}

/** The line as the reader shows it (`line`), else the recorded content, plus the speaker. */
export function interactionMatchesFind(item: FindableLine, needle: string): boolean {
  if (!needle) return true;
  return (
    contains(item.line, needle) ||
    contains(item.content, needle) ||
    contains(item.persona?.name, needle)
  );
}

export function noteMatchesFind(
  note: Pick<FeedNote, 'content' | 'subject'>,
  needle: string
): boolean {
  if (!needle) return true;
  return contains(note.content, needle) || contains(note.subject, needle);
}

export function findInteractions<T extends FindableLine>(items: T[], needle: string): T[] {
  if (!needle) return items;
  return items.filter((item) => interactionMatchesFind(item, needle));
}

export function findNotes<T extends Pick<FeedNote, 'content' | 'subject'>>(
  notes: T[],
  needle: string
): T[] {
  if (!needle) return notes;
  return notes.filter((note) => noteMatchesFind(note, needle));
}

/** The needle the readers mark; empty when no find is active. */
export const FeedFindContext = createContext<string>('');

export function useFeedFind(): string {
  return useContext(FeedFindContext);
}

/**
 * The text with every match wrapped in `<mark>`, as React nodes. Case folds;
 * matches never overlap; with no needle the text comes back as it is.
 */
export function markMatches(text: string, needle: string): ReactNode {
  if (!needle || !text) return text;
  const lower = text.toLowerCase();
  const target = needle.toLowerCase();
  const parts: ReactNode[] = [];
  let from = 0;
  let at = lower.indexOf(target, from);
  if (at === -1) return text;
  while (at !== -1) {
    if (at > from) parts.push(text.slice(from, at));
    parts.push(
      createElement(
        'mark',
        { key: `${at}`, 'data-find-match': '' },
        text.slice(at, at + target.length)
      )
    );
    from = at + target.length;
    at = lower.indexOf(target, from);
  }
  if (from < text.length) parts.push(text.slice(from));
  return parts;
}

/**
 * The same marking for HTML the client did not write (a note's Evennia
 * markup): matches inside text runs are wrapped, tags are left alone.
 */
export function markMatchesInHtml(html: string, needle: string): string {
  if (!needle) return html;
  const target = needle.toLowerCase();
  return html
    .split(/(<[^>]+>)/)
    .map((piece) => {
      if (piece.startsWith('<')) return piece;
      const lower = piece.toLowerCase();
      let out = '';
      let from = 0;
      let at = lower.indexOf(target, from);
      while (at !== -1) {
        out +=
          piece.slice(from, at) +
          '<mark data-find-match="">' +
          piece.slice(at, at + target.length) +
          '</mark>';
        from = at + target.length;
        at = lower.indexOf(target, from);
      }
      return out + piece.slice(from);
    })
    .join('');
}
