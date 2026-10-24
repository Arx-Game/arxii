import { describe, it, expect, vi, beforeEach } from 'vitest';
import { handleCombatEncounterStatePayload } from '../handleCombatEncounterStatePayload';
import { combatKeys } from '@/combat/queries';
import { queryClient } from '@/queryClient';

describe('handleCombatEncounterStatePayload', () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it('refetches the encounter the ping names, and no other', async () => {
    let fetches17 = 0;
    let fetches18 = 0;
    const observe = (id: number, onFetch: () => void) =>
      queryClient.fetchQuery({
        queryKey: combatKeys.encounter(id),
        queryFn: () => {
          onFetch();
          return { id };
        },
      });
    await observe(17, () => (fetches17 += 1));
    await observe(18, () => (fetches18 += 1));
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    handleCombatEncounterStatePayload({ encounter_id: 17, round_number: 3 });

    expect(invalidateSpy).toHaveBeenCalledTimes(1);
    expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: combatKeys.encounter(17) });
    expect(queryClient.getQueryState(combatKeys.encounter(17))?.isInvalidated).toBe(true);
    expect(queryClient.getQueryState(combatKeys.encounter(18))?.isInvalidated).toBe(false);
    expect(fetches17 + fetches18).toBe(2);
  });
});
