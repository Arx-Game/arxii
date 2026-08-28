/**
 * "Offscreen Acts" plate (#3412 slice 3, task 4/5) — the Hall's link-out to
 * the things the docked character can still do without a live `/game`
 * session: write in the journal, log goal progress. Renders only when a
 * character is docked (`gameSlice.activeEntryId`) — an account with nothing
 * docked gets no plate at all, mirroring `CharactersBand`'s docked-card meta
 * line.
 *
 * Persona switching already lives on the portrait cards (`PersonaTiles`,
 * `CharactersBand`) — deliberately NOT duplicated here.
 *
 * Proclamations (#3412 backend slice 3, Task 3): grepped `frontend/src` for
 * `proclaim` — no compose surface exists anywhere in the FE (verified
 * 2026-08-28). Per the boards-row precedent (`AttentionBand`'s doc comment —
 * never ship a link to nothing), the row is OMITTED rather than pointed at a
 * placeholder route. Re-add once a proclamation compose surface exists.
 *
 * Degraded-state display (#3412 slice 3, Task 5 close-out): Task 4 found no
 * FE payload carried the docked character's lifecycle state and deferred
 * this as a follow-up seam. Task 5 closed it: `MyRosterEntry.lifecycle_state`
 * (a display-only `CharField` mirror of the sheet column, added to
 * `MyRosterEntrySerializer` — no migration, no new endpoint) now lets this
 * plate branch. CAPTURED/DEAD/RETIRED/UNKNOWN render the world-voice
 * `DEGRADED_STATE_COPY` prose INSTEAD of the act rows; ALIVE (and the
 * unwritten `LifecycleState.COMA` member, which the backend gate also does
 * not key on — see `actions/constants.py`'s `OFFSCREEN_LIFECYCLE_DISPOSITIONS`
 * comment) keep the rows. This is display-only: the actual gate check still
 * runs server-side at `action.run()` time (`actions.offscreen_gate`) — a
 * stale client-cached `lifecycle_state` can only ever show slightly-wrong
 * copy here, never bypass the real gate.
 *
 * Deliberately NOT surfaced: the unconscious overlay (`unconscious_instance`,
 * a conditions-system read, not a `lifecycle_state` value) — recorded as a
 * seam in the T5 ADR, not built here, per the brief ("do NOT add a
 * conditions query to the serializer").
 */
import { Link } from 'react-router-dom';
import { Plate, PlateHead } from '@/components/folio';
import { useAppSelector } from '@/store/hooks';
import type { MyRosterEntry } from '@/roster/types';

/**
 * The `lifecycle_state` values this plate treats as "still in the story, can
 * still act" — everything else gets the refusal prose. `COMA` is unwritten
 * anywhere in the codebase (no setter exists, #3412 recon) but is included
 * here to mirror the backend gate's own fall-through, not because it's
 * reachable today.
 */
const ALLOWED_LIFECYCLE_STATES = new Set(['ALIVE', 'COMA']);

/**
 * PLACEHOLDER world-voice copy (Garamond/serif body voice, ADR-0243) — final
 * author pass is Dan's to finalize, per the "placeholders now, passes later"
 * project pattern. Deliberately independent of the backend's
 * `OFFSCREEN_REASON_*` strings (`actions/constants.py`): those are told to
 * the actor at the moment they actually attempt a gated act, while this copy
 * is a standing display state on the Hall — same facts, a different register
 * and a different channel name for DEAD (séance, not the backend's silent
 * "no further word" refusal — the Hall speaks for the world, the gate speaks
 * for the dead).
 */
const DEGRADED_STATE_COPY: Record<string, string> = {
  CAPTURED:
    'Word cannot reach you plainly while you are held. Something might still be smuggled out, if someone in the world is willing to carry it.',
  DEAD: 'You have crossed over. Only a séance, held by the living who still remember you, could carry your voice back.',
  RETIRED: 'You have stepped away from the story for now.',
  UNKNOWN: 'Your whereabouts are unknown. There is no way to reach you right now.',
};

const DEFAULT_DEGRADED_COPY = 'You cannot act in the world from here right now.';

export function OffscreenActsPlate({ characters }: { characters: MyRosterEntry[] }) {
  const activeEntryId = useAppSelector((state) => state.game.activeEntryId);
  const docked = characters.find((entry) => entry.id === activeEntryId) ?? null;

  if (!docked) return null;

  const isAllowed = ALLOWED_LIFECYCLE_STATES.has(docked.lifecycle_state);

  return (
    <Plate className="p-4">
      {/* PLACEHOLDER title */}
      <PlateHead as="h2" className="mb-3">
        Offscreen Acts
      </PlateHead>
      {isAllowed ? (
        <ul className="divide-y text-sm">
          <li className="py-1.5">
            <Link to="/journals" className="hover:underline">
              Write in your journal
            </Link>
          </li>
          <li className="py-1.5">
            <Link to="/xp-kudos" className="hover:underline">
              Set your goals
            </Link>
          </li>
        </ul>
      ) : (
        <p className="font-body text-sm italic text-muted-foreground">
          {DEGRADED_STATE_COPY[docked.lifecycle_state] ?? DEFAULT_DEGRADED_COPY}
        </p>
      )}
    </Plate>
  );
}
