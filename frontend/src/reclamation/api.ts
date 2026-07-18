/**
 * Theft-reclamation API client (#2368) — the claimant's own claims and trace.
 *
 * Self-only: the backend scopes every route to the requesting account's own
 * characters. The current holder is never notified a claim exists.
 */

import { apiFetch } from '@/evennia_replacements/api';
import { throwApiError } from '@/lib/errors';

const BASE = '/api/items/reclamation-claims';

export interface TraceStep {
  position: number;
  revealed_text: string;
}

export interface ReclamationClaimRow {
  id: number;
  item_name: string;
  status: string;
  origin: string;
  trace_position: number;
  trace_complete: boolean;
  steps: TraceStep[];
}

export interface ClaimableTheft {
  item: number;
  item_name: string;
}

export async function fetchMyClaims(): Promise<ReclamationClaimRow[]> {
  const res = await apiFetch(`${BASE}/`);
  if (!res.ok) await throwApiError(res, 'Failed to load your claims');
  const data = (await res.json()) as { claims: ReclamationClaimRow[] };
  return data.claims;
}

export async function fetchClaimable(): Promise<ClaimableTheft[]> {
  const res = await apiFetch(`${BASE}/claimable/`);
  if (!res.ok) await throwApiError(res, 'Failed to load your unfiled thefts');
  const data = (await res.json()) as { claimable: ClaimableTheft[] };
  return data.claimable;
}

export async function fileClaim(itemId: number): Promise<ReclamationClaimRow> {
  const res = await apiFetch(`${BASE}/file/`, {
    method: 'POST',
    body: JSON.stringify({ item: itemId }),
  });
  if (!res.ok) await throwApiError(res, 'Failed to file the claim');
  return res.json();
}

export interface AdvanceOutcome {
  claim: ReclamationClaimRow;
  complete: boolean;
  chilled?: boolean;
  holder_revealed?: boolean;
}

export async function advanceTrace(claimId: number): Promise<AdvanceOutcome> {
  const res = await apiFetch(`${BASE}/${claimId}/advance/`, { method: 'POST' });
  if (!res.ok) await throwApiError(res, 'The trace went cold this attempt');
  return res.json();
}

export async function reportClaim(
  claimId: number
): Promise<{ reported: boolean; heat_minted: boolean }> {
  const res = await apiFetch(`${BASE}/${claimId}/report/`, { method: 'POST' });
  if (!res.ok) await throwApiError(res, 'The authorities refused the report');
  return res.json();
}

export async function takeBack(claimId: number): Promise<ReclamationClaimRow> {
  const res = await apiFetch(`${BASE}/${claimId}/take-back/`, { method: 'POST' });
  if (!res.ok) await throwApiError(res, 'The recovery failed');
  return res.json();
}
