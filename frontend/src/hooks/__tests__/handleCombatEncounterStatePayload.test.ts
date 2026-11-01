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

  it("refetches that encounter's rolls for the Last Outcome card, and no other's (#4858)", () => {
    const mine = combatKeys.consequenceOutcomes({ character: 10, encounter: 17, page_size: 2 });
    const other = combatKeys.consequenceOutcomes({ character: 10, encounter: 18, page_size: 2 });
    queryClient.setQueryData(mine, []);
    queryClient.setQueryData(other, []);

    handleCombatEncounterStatePayload({ encounter_id: 17, round_number: 4 });

    expect(queryClient.getQueryState(mine)?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(other)?.isInvalidated).toBe(false);
  });
});
