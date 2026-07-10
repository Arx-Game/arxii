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
