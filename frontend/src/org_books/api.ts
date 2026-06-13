/**
 * Org books API functions (#930 — the family-books / management screen).
 *
 * Covers OrgBooksViewSet (/api/currency/org-books/):
 *   - list: the viewer's own shelf — orgs their presented persona belongs to
 *   - retrieve: the member-visible books for one org
 *
 * Uses apiFetch from @/evennia_replacements/api.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type { components } from '@/generated/api';

// ---------------------------------------------------------------------------
// Generated type aliases
// ---------------------------------------------------------------------------

export type OrgBooks = components['schemas']['OrgBooks'];
export type MyBooksRow = components['schemas']['MyBooksRow'];
export type IncomeStreamRow = components['schemas']['IncomeStreamRow'];
export type DebtRow = components['schemas']['DebtRow'];
export type ObligationRow = components['schemas']['ObligationRow'];
export type ContributionRow = components['schemas']['ContributionRow'];
export type LedgerRow = components['schemas']['LedgerRow'];

// ---------------------------------------------------------------------------
// URL constants
// ---------------------------------------------------------------------------

const ORG_BOOKS_URL = '/api/currency/org-books';

// ---------------------------------------------------------------------------
// Reads
// ---------------------------------------------------------------------------

/** GET /api/currency/org-books/ — orgs whose books the viewer may open. */
export async function getMyBooksShelf(): Promise<MyBooksRow[]> {
  const res = await apiFetch(`${ORG_BOOKS_URL}/`);
  if (!res.ok) throw new Error('Failed to load your organizations');
  return res.json() as Promise<MyBooksRow[]>;
}

/** GET /api/currency/org-books/{orgId}/ — the whole books page in one read. */
export async function getOrgBooks(orgId: number): Promise<OrgBooks> {
  const res = await apiFetch(`${ORG_BOOKS_URL}/${orgId}/`);
  if (!res.ok) {
    if (res.status === 403) throw new Error('You are not a member of that organization.');
    if (res.status === 404) throw new Error('No such organization.');
    throw new Error(`Failed to load books for organization ${orgId}`);
  }
  return res.json() as Promise<OrgBooks>;
}
