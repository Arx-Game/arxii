/**
 * "Offscreen Acts" plate (#3412 slice 3, task 4) — the Hall's link-out to the
 * things the docked character can still do without a live `/game` session:
 * write in the journal, log goal progress. Renders only when a character is
 * docked (`gameSlice.activeEntryId`) — an account with nothing docked gets no
 * plate at all, mirroring `CharactersBand`'s docked-card meta line.
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
 * Degraded-state display (CAPTURED/unconscious/DEAD/RETIRED world-voice
 * refusal prose, per the brief): the only FE payloads that describe the
 * docked character today are `MyRosterEntry` (`roster/types.ts`, sourced from
 * the generated schema) and `AccountData` (`evennia_replacements/types.ts`,
 * hand-rolled) — neither carries `lifecycle_state` or any other gate-derived
 * field (confirmed against `src/generated/api.d.ts`: the only
 * `lifecycle_state` usages in the whole generated schema are unrelated
 * stake-grading fields, nothing on `MyRosterEntry`). Per the brief ("do NOT
 * add a new endpoint without checking what the character payloads already
 * carry"), this plate does not attempt to source or display degraded-state
 * prose — it always renders the allowed rows, and a CAPTURED/DEAD/etc. docked
 * character instead sees the gate's refusal surface where it already lives:
 * inline in the journal composer / goals log-progress dialog when they
 * actually try the act (see `JournalComposerDialog`/`GoalsPanel`'s inline
 * `ApiError` rendering). The exposure seam (a display-only lifecycle/gate
 * field on `MyRosterEntry` or `AccountData`) is left for a follow-up task.
 */
import { Link } from 'react-router-dom';
import { Plate, PlateHead } from '@/components/folio';
import { useAppSelector } from '@/store/hooks';
import type { MyRosterEntry } from '@/roster/types';

export function OffscreenActsPlate({ characters }: { characters: MyRosterEntry[] }) {
  const activeEntryId = useAppSelector((state) => state.game.activeEntryId);
  const docked = characters.find((entry) => entry.id === activeEntryId) ?? null;

  if (!docked) return null;

  return (
    <Plate className="p-4">
      {/* PLACEHOLDER title */}
      <PlateHead as="h2" className="mb-3">
        Offscreen Acts
      </PlateHead>
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
    </Plate>
  );
}
