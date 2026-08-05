/** Kin tree + pairwise relationship REST calls (#2062, #3003). */
import { apiFetch } from '@/evennia_replacements/api';

import type { FamilyTree, KinRelationship } from './types';

const ROSTER_URL = '/api/roster';

/** Viewer-aware kin tree centred on a character. `characterId` is a CharacterSheet pk. */
export async function getKinTree(characterId: number): Promise<FamilyTree> {
  const res = await apiFetch(`${ROSTER_URL}/kin/tree/${characterId}/`);
  if (!res.ok) {
    throw new Error('Failed to load kin tree');
  }
  return res.json() as Promise<FamilyTree>;
}

/** Viewer-derived relationship label between two characters. `a`/`b` are CharacterSheet pks. */
export async function getKinRelationship(a: number, b: number): Promise<KinRelationship> {
  const params = new URLSearchParams({ a: String(a), b: String(b) });
  const res = await apiFetch(`${ROSTER_URL}/kin/relationship/?${params.toString()}`);
  if (!res.ok) {
    throw new Error('Failed to load relationship');
  }
  return res.json() as Promise<KinRelationship>;
}
