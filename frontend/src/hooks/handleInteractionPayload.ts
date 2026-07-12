import { toast } from 'sonner';
import type { NavigateFunction } from 'react-router-dom';
import type { InteractionWsPayload } from './types';
import type { AppDispatch } from '@/store/store';
import { store } from '@/store/store';
import { addSceneInteraction, openThreadTab, setActiveSession } from '@/store/gameSlice';
import type { MyRosterEntry } from '@/roster/types';
import { queryClient } from '@/queryClient';
import { getThreadKey } from '@/scenes/hooks/useThreading';
import { wsPayloadToInteraction } from '@/scenes/hooks/useSceneInteractions';

export function handleInteractionPayload(
  character: MyRosterEntry['name'],
  payload: InteractionWsPayload,
  dispatch: AppDispatch,
  navigate: NavigateFunction
) {
  dispatch(addSceneInteraction({ character, interaction: payload }));
  maybeToastWhisperAttention(character, payload, dispatch, navigate);
}

/**
 * Interaction ids already toasted (#2166) — mirrors DuelChallengeNotifier's
 * `toastedIds` dedupe idiom, but module-level rather than a ref: this file has
 * no component instance, and `useGameSocket` opens one socket per character
 * (a fresh mount doesn't replay past frames), so a plain module `Set` is safe.
 */
const toastedWhisperIds = new Set<number>();

/**
 * Own-persona detection (#2166 Task 3 decision, documented per the plan's
 * framework): a session's own persona id is NOT in Redux (only the roster
 * query has it), so this reads `primary_persona_id` for the RECEIVING
 * character straight out of the React Query cache via `queryClient
 * .getQueryData(['my-roster-entries'])` — the same cache
 * `useMyRosterEntriesQuery` populates, and the same field (`primary_persona_id`)
 * Task 2's `sessionAttention` call sites already use as "this session's
 * persona" for thread-key grouping, so the definition of "my persona" stays
 * consistent across the badge and the toast. By the time any socket message
 * arrives the roster has always already been fetched (a session can't exist
 * without the roster resolving the character first), so the cache is expected
 * to be warm; if it is ever empty (`ownPersonaId` stays `null`) this
 * deliberately does NOT suppress the toast — per the plan's documented MVP
 * fallback, a false-positive toast on a rare self-echo is preferable to
 * silently dropping a real cross-character whisper.
 */
function ownPersonaId(character: MyRosterEntry['name']): number | null {
  const rosterEntries = queryClient.getQueryData<MyRosterEntry[]>(['my-roster-entries']);
  return rosterEntries?.find((entry) => entry.name === character)?.primary_persona_id ?? null;
}

function maybeToastWhisperAttention(
  character: MyRosterEntry['name'],
  payload: InteractionWsPayload,
  dispatch: AppDispatch,
  navigate: NavigateFunction
) {
  if (payload.mode !== 'whisper') return;

  const activeCharacter = store.getState().game.active;
  if (character === activeCharacter) return;

  const myPersonaId = ownPersonaId(character);
  if (myPersonaId != null && payload.persona.id === myPersonaId) return;

  if (toastedWhisperIds.has(payload.id)) return;
  toastedWhisperIds.add(payload.id);

  const threadKey = getThreadKey(wsPayloadToInteraction(payload));

  toast(`Whisper to ${character} from ${payload.persona.name}`, {
    action: {
      label: 'Switch',
      onClick: () => {
        dispatch(setActiveSession(character));
        dispatch(openThreadTab({ character, threadKey }));
        if (window.location.pathname !== '/game') {
          navigate('/game');
        }
      },
    },
  });
}
