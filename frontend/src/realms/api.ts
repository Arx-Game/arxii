/**
 * Realm page reads (#3725) — anonymous-safe by construction (ADR-0285).
 *
 * The hub reads the realm list; a realm page reads the realm by slug, then its
 * organizations (shop-window fields only; covert kinds only to their members) and
 * its two boards (names and band labels, never a number). The realm's roster comes
 * through the roster module's own read with the `realm` filter.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { RealmBoards, RealmDetail, RealmListItem, RealmOrganization } from './types';

export async function getRealms(): Promise<RealmListItem[]> {
  const res = await apiFetch('/api/realms/');
  if (!res.ok) {
    throw new Error('Failed to load realms');
  }
  return res.json();
}

export async function getRealm(slug: string): Promise<RealmDetail> {
  const res = await apiFetch(`/api/realms/${encodeURIComponent(slug)}/`);
  if (!res.ok) {
    throw new Error('Failed to load realm');
  }
  return res.json();
}

export async function getRealmOrganizations(slug: string): Promise<RealmOrganization[]> {
  const res = await apiFetch(`/api/realms/${encodeURIComponent(slug)}/organizations/`);
  if (!res.ok) {
    throw new Error('Failed to load realm organizations');
  }
  return res.json();
}

export async function getRealmNotables(slug: string): Promise<RealmBoards> {
  const res = await apiFetch(`/api/realms/${encodeURIComponent(slug)}/notables/`);
  if (!res.ok) {
    throw new Error('Failed to load realm notables');
  }
  return res.json();
}
