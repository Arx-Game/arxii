/**
 * DreamspacePanel — takes over the play view's Room tab while a character
 * is dreamside (#3003).
 *
 * ATMOSPHERE: dreaming is a PLACE the character is, not a status effect they
 * carry. This panel is deliberately styled distinct from the waking
 * `RoomPanel` (indigo/violet gradient, moon iconography, italic room prose)
 * so switching into a dream reads as stepping through a door, not toggling a
 * badge. `GamePage` swaps it in for `FocusPanel` whenever `useDreamState`
 * reports `is_dreamside` — the same rule the server already applies to
 * `look` and the `room_state` websocket push, so web and telnet agree by
 * construction.
 *
 * Every unavailable control renders DISABLED with its reason visible,
 * reusing the exact backend copy so the rules teach themselves through the
 * UI rather than diverging from what telnet players see:
 * - Wake: `wake_blocked` -> "You are lost in the dream; you cannot wake
 *   until the danger passes." (`actions/definitions/vitals.py`, `WakeAction`)
 * - Descend: no `can_descend` -> "There is no deeper dream to descend into
 *   from here." (`actions/definitions/dreams.py`, `DescendAction`)
 * - Ascend: no `can_ascend` -> "You cannot find your way back from here."
 *   (`actions/definitions/dreams.py`, `AscendAction`)
 *
 * Refresh: subscribes to `useActionResult` and invalidates the dream-state
 * query on every action result (not just this panel's own dispatches), so
 * peril outcomes, forced wakes, and a co-dreamer's arrival all surface
 * without polling.
 */

import { useCallback } from 'react';
import { ArrowDown, ArrowUp, Moon, Wind } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';

import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useActionResult } from '@/hooks/actionResultBus';
import type { ActionResultPayload } from '@/hooks/types';
import { useGameSocket } from '@/hooks/useGameSocket';

import { dreamKeys, useDreamState } from '../queries';

const WAKE_BLOCKED_REASON = 'You are lost in the dream; you cannot wake until the danger passes.';
const NO_DESCENT_REASON = 'There is no deeper dream to descend into from here.';
const NO_ASCENT_REASON = 'You cannot find your way back from here.';

interface DreamspacePanelProps {
  characterId: number;
  characterName: string;
}

export function DreamspacePanel({ characterId, characterName }: DreamspacePanelProps) {
  const { data, isLoading } = useDreamState(characterId);
  const { executeAction } = useGameSocket();
  const queryClient = useQueryClient();

  const handleActionResult = useCallback(
    (_payload: ActionResultPayload) => {
      queryClient.invalidateQueries({ queryKey: dreamKeys.state(characterId) }).catch(() => {});
    },
    [characterId, queryClient]
  );
  useActionResult(handleActionResult);

  const dispatch = useCallback(
    (key: string, kwargs: Record<string, unknown> = {}) => {
      executeAction(characterName, key, kwargs);
    },
    [characterName, executeAction]
  );

  if (isLoading) {
    return (
      <div
        data-testid="dreamspace-panel-loading"
        className="flex h-full flex-col gap-3 bg-gradient-to-b from-indigo-950/10 to-transparent p-4"
      >
        <Skeleton className="h-4 w-2/3" />
        <Skeleton className="h-4 w-full" />
        <Skeleton className="h-4 w-full" />
      </div>
    );
  }

  if (!data || !data.is_dreamside) {
    return <div className="p-4 text-sm text-muted-foreground">The dream has faded.</div>;
  }

  const {
    dream_room: dreamRoom,
    co_dreamers: coDreamers,
    dreamwalk_host: dreamwalkHost,
    dreamwalk_candidates: dreamwalkCandidates,
    can_descend: canDescend,
    descent_name: descentName,
    can_ascend: canAscend,
    wake_blocked: wakeBlocked,
  } = data;

  return (
    <div
      data-testid="dreamspace-panel"
      className="flex h-full flex-col gap-4 bg-gradient-to-b from-indigo-950/20 via-indigo-950/10 to-transparent p-4 text-indigo-100"
    >
      <div className="flex items-center gap-2 text-indigo-300">
        <Moon className="h-4 w-4" />
        <span className="text-xs font-medium uppercase tracking-wide">Dreaming</span>
      </div>

      {dreamRoom ? (
        <div className="space-y-1">
          <h3 className="text-base font-semibold text-indigo-50">{dreamRoom.key}</h3>
          <p className="text-sm italic text-indigo-200/80">{dreamRoom.description}</p>
        </div>
      ) : (
        <p className="text-sm italic text-indigo-200/80">The dream has no shape here yet.</p>
      )}

      {dreamwalkHost && (
        <p className="text-xs text-indigo-300/80">
          You have dreamwalked into {dreamwalkHost.name}'s dream.
        </p>
      )}

      <section aria-label="Co-dreamers" className="space-y-1">
        <p className="text-xs font-medium uppercase tracking-wide text-indigo-300">
          Sharing this dream
        </p>
        {coDreamers.length === 0 ? (
          <p className="text-sm text-indigo-200/60">You are alone in this dream.</p>
        ) : (
          <ul className="space-y-0.5 text-sm text-indigo-100">
            {coDreamers.map((dreamer) => (
              <li key={dreamer.id}>{dreamer.name}</li>
            ))}
          </ul>
        )}
      </section>

      <section aria-label="Dreamwalk" className="space-y-1">
        <p className="text-xs font-medium uppercase tracking-wide text-indigo-300">Dreamwalk</p>
        {dreamwalkCandidates.length === 0 ? (
          <p className="text-sm text-indigo-200/60">No one within reach to dreamwalk to.</p>
        ) : (
          <div className="flex flex-wrap gap-1.5">
            {dreamwalkCandidates.map((candidate) => (
              <Button
                key={candidate.id}
                size="sm"
                variant="outline"
                className="border-indigo-700/50 text-indigo-100 hover:bg-indigo-900/40"
                onClick={() => dispatch('dreamwalk', { target: candidate.id })}
              >
                <Wind className="mr-1 h-3 w-3" />
                {candidate.name}
              </Button>
            ))}
          </div>
        )}
      </section>

      <section
        aria-label="Dream controls"
        className="mt-auto space-y-2 border-t border-indigo-800/40 pt-3"
      >
        <div className="flex flex-col gap-1">
          <Button
            size="sm"
            variant="outline"
            className="justify-start border-indigo-700/50 text-indigo-100 hover:bg-indigo-900/40"
            disabled={wakeBlocked}
            onClick={() => dispatch('wake')}
          >
            Wake
          </Button>
          {wakeBlocked && <p className="text-xs text-red-300">{WAKE_BLOCKED_REASON}</p>}
        </div>

        <div className="flex flex-col gap-1">
          <Button
            size="sm"
            variant="outline"
            className="justify-start border-indigo-700/50 text-indigo-100 hover:bg-indigo-900/40"
            disabled={!canDescend}
            onClick={() => dispatch('descend')}
          >
            <ArrowDown className="mr-1 h-3 w-3" />
            {canDescend && descentName ? `Descend to ${descentName}` : 'Descend'}
          </Button>
          {!canDescend && <p className="text-xs text-indigo-300/70">{NO_DESCENT_REASON}</p>}
        </div>

        <div className="flex flex-col gap-1">
          <Button
            size="sm"
            variant="outline"
            className="justify-start border-indigo-700/50 text-indigo-100 hover:bg-indigo-900/40"
            disabled={!canAscend}
            onClick={() => dispatch('ascend')}
          >
            <ArrowUp className="mr-1 h-3 w-3" />
            Ascend
          </Button>
          {!canAscend && <p className="text-xs text-indigo-300/70">{NO_ASCENT_REASON}</p>}
        </div>
      </section>
    </div>
  );
}
