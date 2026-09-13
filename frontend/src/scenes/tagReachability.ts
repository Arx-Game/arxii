import type { RoomStateObject } from '@/hooks/types';
import type { ViewerVenue } from './replyReachability';

export interface TagRefusal {
  reachable: boolean;
  /** The bold refusal sentence (demo Screen 3's `.refusal strong`). */
  reason?: string;
  /** The quieter follow-on line naming where to go instead (`.refusal .fix`). */
  hint?: string;
}

const REACHABLE: TagRefusal = { reachable: true };

/**
 * Mirrors the server's own copy verbatim
 * (`world.scenes.interaction_services._TARGET_UNREACHABLE_HINT` /
 * `_describe_unreachable_targets`), rather than inventing client-side wording,
 * exactly as `replyReachability` already does for the reply case.
 */
const TARGET_UNREACHABLE_HINT =
  'Address the room to reach them, or send a whisper. Your draft is kept.';

function describeUnreachableTargets(names: string[]): string {
  if (names.length === 1) {
    return `${names[0]} is across the room and will not see table talk.`;
  }
  const joined = names.slice(0, -1).join(', ') + ` and ${names[names.length - 1]}`;
  return `${joined} are across the room and will not see table talk.`;
}

/**
 * Client-side mirror of `persona_can_receive`'s reachability rules, checked
 * against `composerMode.targets` (#3810) rather than the composer's free-text
 * prose (which is never sent to the server as a target at all). `mode` is
 * `composerMode.command`: whisper is always reachable for its own named
 * targets (receiver-based, never location-based, mirroring
 * `persona_can_receive`'s whisper branch); every other mode checks physical
 * presence, and a Place-scoped mode additionally requires the target share
 * the actor's own current Place.
 */
export function tagReachability(
  targetNames: string[],
  roomCharacters: RoomStateObject[],
  mode: string,
  venue: ViewerVenue
): TagRefusal {
  if (targetNames.length === 0 || mode === 'whisper') {
    return REACHABLE;
  }

  const byLowerName = new Map(
    roomCharacters.map((character) => [character.name.toLowerCase(), character])
  );

  const unreachable = targetNames.filter((name) => {
    const character = byLowerName.get(name.toLowerCase());
    if (!character) {
      // Not physically in the room at all: unreachable regardless of mode.
      return true;
    }
    if (venue.isAtPlace) {
      return character.place_id !== venue.currentPlaceId;
    }
    // Room-wide: being found in roomCharacters already satisfies room-heard's
    // physical-presence requirement.
    return false;
  });

  if (unreachable.length === 0) {
    return REACHABLE;
  }

  return {
    reachable: false,
    reason: describeUnreachableTargets(unreachable),
    hint: TARGET_UNREACHABLE_HINT,
  };
}
