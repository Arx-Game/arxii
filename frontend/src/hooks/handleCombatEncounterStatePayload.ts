import { combatKeys } from '@/combat/queries';
import { queryClient } from '@/queryClient';

/**
 * Payload for the ``combat_encounter_state`` WS message (``CombatEncounterStatePayload``
 * in ``src/web/webclient/message_types.py``). Hand-authored mirror of the backend
 * dataclass, same convention as ``BattleStatePayload``.
 */
export interface CombatEncounterStatePayload {
  encounter_id: number;
  round_number: number;
}

/**
 * A combat change committed (a round resolved, someone moved): refetch that
 * encounter so the battle map shows where everyone now stands (#4644). The server
 * sends this after the commit, so the refetch reads the new state; the outcome
 * lines a round pushes arrive before it commits.
 */
export function handleCombatEncounterStatePayload(payload: CombatEncounterStatePayload) {
  void queryClient.invalidateQueries({ queryKey: combatKeys.encounter(payload.encounter_id) });
}
