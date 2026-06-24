/** Public-reaction tidings feed REST calls (#1450). */
import { apiFetch } from '@/evennia_replacements/api';

import type { PublicFeedItem } from './types';

/** Recent public events (deeds + scandals) the active viewing character's societies are aware of.
 * `viewerId` is the active character's RosterEntry pk — IC awareness is per character, never the
 * account. */
export async function fetchPublicFeed(viewerId: number): Promise<PublicFeedItem[]> {
  const res = await apiFetch(`/api/tidings/feed/?viewer=${viewerId}`);
  if (!res.ok) {
    throw new Error('Failed to load the tidings feed');
  }
  return res.json() as Promise<PublicFeedItem[]>;
}
