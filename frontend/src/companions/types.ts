/** Companion API types (#672, #3294). Hand-maintained, mirroring the shape of
 * `world.companions.serializers.CompanionSerializer` — see `frontend/src/scenes/types.ts`
 * for the same hand-typed convention on `Interaction`. */

export interface CompanionArchetypeSummary {
  id: number;
  domain: string;
  name: string;
  description: string;
  bind_difficulty: number;
  capacity_cost: number;
}

export interface CompanionSummary {
  id: number;
  name: string;
  archetype: CompanionArchetypeSummary;
  bonded_at: string;
  released_at: string | null;
  /** True when the companion's live object shares the actor's current room (#3294) —
   * gates the composer's "as <companion>" emote toggle. */
  is_present: boolean;
}

export interface CompanionListResponse {
  results: CompanionSummary[];
}
