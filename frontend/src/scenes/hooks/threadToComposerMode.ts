import type { Thread } from './useThreading';
import type { ComposerMode } from '@/game/components/CommandInput';

/**
 * Translates a scene thread into the CommandInput composer mode that targets
 * it: room threads pose broadly, place threads use tabletalk, whisper threads
 * address their private audience, and ad-hoc target threads @-mention the
 * thread's participants.
 *
 * Extracted from `SceneInteractionPanel` (#2156) so `GamePage` — the new
 * composition root for `/game` — can reuse the same thread→composer
 * translation without duplicating it.
 */
export function threadToComposerMode(thread: Thread, roomName: string): ComposerMode {
  switch (thread.type) {
    case 'room':
      return { command: 'pose', targets: [], label: `Pose → ${roomName}` };
    case 'place':
      return { command: 'tt', targets: [], label: `TT → ${thread.label}` };
    case 'whisper':
      return {
        command: 'whisper',
        targets: thread.participantPersonas.map((p) => p.name),
        label: `Whisper → ${thread.label.replace('Whisper: ', '')}`,
      };
    case 'target':
      return {
        command: 'pose',
        targets: thread.participantPersonas.map((p) => p.name),
        label: `Pose → ${thread.label}`,
      };
  }
}

/**
 * Composer mode for an open conversation TAB (#2165) — always `locked`.
 * Prefers the resolved thread; a restored tab whose thread hasn't backfilled
 * yet derives a safe audience from the key shape alone. An unresolved whisper
 * key yields `targets: []`, which CommandInput's whisper guard refuses to
 * send — fail-closed beats mis-sending to the room.
 */
export function tabKeyToComposerMode(
  key: string,
  threads: Thread[],
  roomName: string
): ComposerMode {
  const thread = threads.find((t) => t.key === key);
  if (thread) return { ...threadToComposerMode(thread, roomName), locked: true };
  if (key.startsWith('place:')) {
    return { command: 'tt', targets: [], label: 'Tabletalk', locked: true };
  }
  if (key.startsWith('whisper:')) {
    return { command: 'whisper', targets: [], label: 'Whisper', locked: true };
  }
  return { command: 'pose', targets: [], label: `Pose → ${roomName}`, locked: true };
}
