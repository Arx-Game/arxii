/**
 * Kinship graph types (#2062, #3003), from the generated OpenAPI schema.
 *
 * Moved here from `character-creation/types.ts`, which defined these by hand before
 * Task 7 landed named schema components for them — see the generated-types re-export
 * convention in `friends/types.ts`. `KinSlot`/`KinSlotPool`/`FamilySlots` stay in
 * `character-creation` — the CG slot picker still owns and uses them.
 */
import type { components } from '@/generated/api';

/** Viewer-aware graph payload for GET /api/roster/kin/tree/<character_id>/. */
export type FamilyTree = components['schemas']['FamilyTree'];

/** One visible node in a family tree payload. `id` is a Kinsperson pk (NOT a
 * CharacterSheet pk) — see `sheet_id` for the bound CharacterSheet, when any. */
export type KinspersonNode = components['schemas']['KinspersonNode'];

/** One visible parentage edge in a family tree payload. */
export type ParentageEdge = components['schemas']['ParentageEdge'];

/** One visible union in a family tree payload. */
export type UnionEdge = components['schemas']['UnionEdge'];

/** Response for GET /api/roster/kin/relationship/?a=&b=. */
export type KinRelationship = components['schemas']['KinRelationship'];
