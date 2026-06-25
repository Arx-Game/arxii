import { apiFetch } from '@/evennia_replacements/api';

/** A `who` row: an online character's active-persona name + a coarse idle state. */
export interface WhoEntry {
  name: string;
  /** "" (active), "idle", or "away" — deliberately coarse (never exact minutes). */
  idle: string;
}

/** A `where` row: a present character + its Evennia-colour-coded room path. */
export interface WhereEntry {
  persona_name: string;
  room_path: string;
}

export interface PresencePayload {
  who: WhoEntry[];
  where: WhereEntry[];
}

/** GET the online presence (who + where) for the game-view presence panel (#1463). */
export async function getPresence(): Promise<PresencePayload> {
  const res = await apiFetch('/api/areas/presence/');
  if (!res.ok) {
    throw new Error('Failed to load presence.');
  }
  return res.json() as Promise<PresencePayload>;
}
