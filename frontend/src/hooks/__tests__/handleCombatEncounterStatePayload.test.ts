import { describe, it, expect } from 'vitest';
import { handleCombatEncounterStatePayload } from '../handleCombatEncounterStatePayload';
import { combatKeys } from '@/combat/queries';
import { queryClient } from '@/queryClient';

// A handler unit: the socket routes the frame here, and no journey reaches the browser cache.
describe('handleCombatEncounterStatePayload', () => {
  it('marks the encounter the ping names stale, and no other', () => {
    queryClient.setQueryData(combatKeys.encounter(17), { id: 17 });
    queryClient.setQueryData(combatKeys.encounter(18), { id: 18 });

    handleCombatEncounterStatePayload({ encounter_id: 17, round_number: 3 });

    expect(queryClient.getQueryState(combatKeys.encounter(17))?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(combatKeys.encounter(18))?.isInvalidated).toBe(false);
  });
});
