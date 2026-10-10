import type { FeedNote } from '@/hooks/types';
import type { Interaction } from '@/scenes/types';
import {
  groupThreads,
  type Thread,
  type ThreadPersona,
  type UseThreadingOpts,
} from '@/scenes/hooks/useThreading';

/**
 * The conversation rail's rows (#4129): what the current character is in,
 * grouped and ordered, as pure data. The rail draws these; `GamePage` builds
 * them from the scene's threads, the quiet room's ambient interactions and the
 * session's page notes.
 */
export type RailRowKind = 'room' | 'thread' | 'place' | 'whisper' | 'page';

export interface RailRow {
  /** The thread key the row selects: `room`, a thread key, or `page:<persona id>`. */
  key: string;
  kind: RailRowKind;
  label: string;
  /** The one person the conversation is with, when it is one person's: a whisper, a page. */
  person: ThreadPersona | null;
  unreadCount: number;
  latestTimestamp: string;
}

export interface RailGroups {
  here: RailRow[];
  pages: RailRow[];
}

export interface RailRowsInput {
  /** The scene's threads, from `useThreading`; empty with no scene. */
  threads: Thread[];
  /** The quiet room's scene-less interactions, grouped here the same way. */
  ambientInteractions: Interaction[];
  /** The session's notes; only page notes with a correspondent become rows. */
  notes: FeedNote[];
  /** The room's own name, the room row's label (the composer names the scene instead). */
  roomName: string;
  viewerPersonaId: number | null;
  lastSeenByThread: Record<string, number>;
  sceneBaselineId: number | null;
}

/** The kind word a row shows beside its name; the room shows none. */
export const RAIL_KIND_WORDS: Record<RailRowKind, string> = {
  room: '',
  thread: 'thread',
  place: 'tabletalk',
  whisper: 'whisper',
  page: 'page',
};

/** The key a page conversation selects: the correspondent's persona. */
export function pageRowKey(personaId: number): string {
  return `page:${personaId}`;
}

export function isPageRowKey(key: string | null): key is string {
  return key !== null && key.startsWith('page:');
}

function othersIn(thread: Thread, viewerPersonaId: number | null): ThreadPersona[] {
  const others = thread.participantPersonas.filter((p) => p.id !== viewerPersonaId);
  return others.length > 0 ? others : thread.participantPersonas;
}

function rowFromThread(thread: Thread, viewerPersonaId: number | null, roomName: string): RailRow {
  if (thread.type === 'room') {
    return {
      key: 'room',
      kind: 'room',
      label: roomName,
      person: null,
      unreadCount: thread.unreadCount,
      latestTimestamp: thread.latestTimestamp,
    };
  }
  if (thread.type === 'whisper') {
    const others = othersIn(thread, viewerPersonaId);
    return {
      key: thread.key,
      kind: 'whisper',
      label: others.map((p) => p.name).join(', '),
      person: others.length === 1 ? others[0] : null,
      unreadCount: thread.unreadCount,
      latestTimestamp: thread.latestTimestamp,
    };
  }
  return {
    key: thread.key,
    kind: thread.type === 'place' ? 'place' : 'thread',
    label: thread.label,
    person: null,
    unreadCount: thread.unreadCount,
    latestTimestamp: thread.latestTimestamp,
  };
}

/** Two rows for one key, from the scene and from the quiet room: one row, both counted. */
function mergeRows(a: RailRow, b: RailRow): RailRow {
  return {
    ...a,
    person: a.person ?? b.person,
    unreadCount: a.unreadCount + b.unreadCount,
    latestTimestamp: a.latestTimestamp >= b.latestTimestamp ? a.latestTimestamp : b.latestTimestamp,
  };
}

function newestFirst(rows: RailRow[]): RailRow[] {
  return [...rows].sort((a, b) => b.latestTimestamp.localeCompare(a.latestTimestamp));
}

/**
 * Page rows (#4129, PR 2): one per correspondent, from the session's page
 * notes. A page is a note, so its unread count is the notes newer than the
 * row's last-seen mark, which for a page row is a time rather than an id;
 * the correspondent's own lines count, the viewer's echoes never do.
 */
function pageRows(notes: FeedNote[], lastSeenByThread: Record<string, number>): RailRow[] {
  const byPersona = new Map<number, RailRow>();
  for (const note of notes) {
    if (note.kind !== 'page' || !note.from) continue;
    const key = pageRowKey(note.from.personaId);
    const seenAt = lastSeenByThread[key] ?? 0;
    const unread = !note.outgoing && Date.parse(note.timestamp) > seenAt ? 1 : 0;
    const existing = byPersona.get(note.from.personaId);
    if (existing) {
      existing.unreadCount += unread;
      if (note.timestamp > existing.latestTimestamp) existing.latestTimestamp = note.timestamp;
      continue;
    }
    byPersona.set(note.from.personaId, {
      key,
      kind: 'page',
      label: note.from.name,
      person: { id: note.from.personaId, name: note.from.name, thumbnailUrl: null },
      unreadCount: unread,
      latestTimestamp: note.timestamp,
    });
  }
  return newestFirst([...byPersona.values()]);
}

/**
 * Every conversation the character is in, grouped: **Here** (the room first,
 * then its threads, places and whispers, the quiet room's grouped the same
 * way) and **OOC Pages**. Newest activity first within a group. The room row
 * is always drawn once there is a room; everything else only when it has
 * lines.
 */
export function buildRailRows(input: RailRowsInput): RailGroups {
  const opts: UseThreadingOpts = {
    lastSeenByThread: input.lastSeenByThread,
    viewerPersonaId: input.viewerPersonaId,
    // A quiet room has no scene baseline: everything that arrives is unread
    // until its row is read.
    sceneBaselineId: input.sceneBaselineId ?? 0,
  };
  const ambient = groupThreads(input.ambientInteractions, input.roomName, opts).threads;
  const byKey = new Map<string, RailRow>();
  for (const thread of [...input.threads, ...ambient]) {
    const row = rowFromThread(thread, input.viewerPersonaId, input.roomName);
    const existing = byKey.get(row.key);
    byKey.set(row.key, existing ? mergeRows(existing, row) : row);
  }
  const room: RailRow = byKey.get('room') ?? {
    key: 'room',
    kind: 'room',
    label: input.roomName,
    person: null,
    unreadCount: 0,
    latestTimestamp: '',
  };
  byKey.delete('room');
  return {
    here: [room, ...newestFirst([...byKey.values()])],
    pages: pageRows(input.notes, input.lastSeenByThread),
  };
}

/** Every row of both groups, for the folded strip and the selection lookup. */
export function allRailRows(groups: RailGroups): RailRow[] {
  return [...groups.here, ...groups.pages];
}
