/**
 * ConsentAttentionNotifier — site-wide alert for a pending consent/action
 * request addressed to ANY of the account's played characters (#2166).
 *
 * Mirrors `DuelChallengeNotifier` (#2157): mounted once at the app root
 * (`App.tsx`, beside it), polls ACCOUNT-WIDE rather than per-scene
 * (`GET /api/action-requests/?status=pending&role=incoming` —
 * `SceneActionRequestFilter.role`, added for this task; the underlying
 * queryset was already scoped to the caller's own personas via
 * `get_account_personas`, so `role=incoming` only narrows *which side* —
 * target, not initiator — of that already-owned set to keep; it never leaks
 * another player's requests), and fires one toast per newly-seen pending
 * request id.
 *
 * Dedupe uses a module-level `Set` with the 500-cap idiom from
 * `handleInteractionPayload.ts` (#2166 Task 3) rather than a component ref —
 * the poll (not a per-character socket) is this component's data source, and
 * a `Set` survives remounts the same way that file's does.
 *
 * NO accept/deny here — the in-scene `ConsentPrompt` owns the graded response
 * (plausibility band, resist effort, blacklist-actor). Clicking the toast
 * only switches to the addressed character — starting a session first if
 * none is live yet, mirroring `GameTopBar.handleSelectCharacter` — and
 * navigates to `/game`, where `ConsentPrompt`'s own per-scene poll picks the
 * request up from there.
 *
 * Character resolution (#2166, documented per the plan's decision framework):
 * `target_persona` is a Persona pk, not a CharacterSheet id, so unlike
 * `DuelChallengeNotifier` (whose `challenged.id` IS the CharacterSheet pk and
 * matches `MyRosterEntry.character_id` directly) this can't be resolved with
 * a single equality check. It is matched against each roster entry's own
 * `primary_persona_id` first — the same "this session's own persona"
 * definition Task 2's `sessionAttention` call sites and Task 3's
 * `ownPersonaId` (`handleInteractionPayload.ts`) already use, kept consistent
 * here rather than introducing a third definition — then against
 * `active_persona_id` (the currently-worn face), which additionally covers
 * the common case of a request addressed to a mask while it's still worn. A
 * request addressed to a mask the player has since put away is a rare edge
 * this toast still fires for (falls back to the raw `target_name` label with
 * no session-switch on click, rather than being silently dropped).
 *
 * Renders nothing itself — `null` always, purely a side-effect component.
 */

import { useEffect } from 'react';
import { useQuery } from '@tanstack/react-query';
import { toast } from 'sonner';
import { useNavigate } from 'react-router-dom';
import { useAppDispatch, useAppSelector } from '@/store/hooks';
import { setActiveSession, startSession } from '@/store/gameSlice';
import { useGameSocket } from '@/hooks/useGameSocket';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import type { MyRosterEntry } from '@/roster/types';
import { fetchIncomingConsentRequests } from '../actionQueries';
import type { IncomingConsentRequest } from '../actionTypes';

const toastedRequestIds = new Set<number>();
const MAX_TOASTED_REQUEST_IDS = 500;

function resolveTargetCharacter(
  request: IncomingConsentRequest,
  myRosterEntries: MyRosterEntry[]
): MyRosterEntry | null {
  return (
    myRosterEntries.find((e) => e.primary_persona_id === request.target_persona) ??
    myRosterEntries.find((e) => e.active_persona_id === request.target_persona) ??
    null
  );
}

export function ConsentAttentionNotifier() {
  const dispatch = useAppDispatch();
  const navigate = useNavigate();
  const { connect } = useGameSocket();
  const sessions = useAppSelector((state) => state.game.sessions);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();

  const { data } = useQuery({
    queryKey: ['incoming-consent-requests'],
    queryFn: fetchIncomingConsentRequests,
    enabled: myRosterEntries.length > 0,
    refetchInterval: 15_000,
    staleTime: 10_000,
  });
  useEffect(() => {
    const pendingRequests = data?.results ?? [];
    for (const request of pendingRequests) {
      if (toastedRequestIds.has(request.id)) continue;
      if (toastedRequestIds.size > MAX_TOASTED_REQUEST_IDS) toastedRequestIds.clear();
      toastedRequestIds.add(request.id);

      const targetEntry = resolveTargetCharacter(request, myRosterEntries);
      const characterName = targetEntry?.name ?? request.target_name;
      const actionLabel = request.technique_name ?? request.action_key;

      toast(`Consent request for ${characterName}: ${actionLabel} from ${request.initiator_name}`, {
        action: {
          label: 'View',
          onClick: () => {
            if (targetEntry) {
              if (sessions[targetEntry.name]) {
                dispatch(setActiveSession(targetEntry.name));
                if (!sessions[targetEntry.name].isConnected) {
                  connect(targetEntry.name);
                }
              } else {
                dispatch(startSession(targetEntry.name));
                connect(targetEntry.name);
              }
            }
            if (window.location.pathname !== '/game') {
              navigate('/game');
            }
          },
        },
      });
    }
  }, [data, myRosterEntries, sessions, dispatch, navigate, connect]);

  return null;
}
