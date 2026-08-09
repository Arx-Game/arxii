/**
 * Types for progression data (XP and Kudos).
 */

import type { components } from '@/generated/api';

// ---------------------------------------------------------------------------
// Unlock shop (#3045) — re-exports of generated schema components. Backend:
// world.progression.serializers.unlocks / ProgressionUnlockViewSet.
// ---------------------------------------------------------------------------

/** A single purchasable unlock row (class_level / thread_xp_lock / skill_breakthrough). */
export type ProgressionUnlockItem = components['schemas']['ProgressionUnlockItem'];
export type PaginatedProgressionUnlockItemList =
  components['schemas']['PaginatedProgressionUnlockItemList'];
export type PurchaseUnlockRequest = components['schemas']['PurchaseUnlockRequest'];
export type PurchaseUnlockResponse = components['schemas']['PurchaseUnlockResponse'];

// ---------------------------------------------------------------------------
// Durance readiness hub (#3045) — re-exports of generated schema components.
// Backend: world.progression.serializers.durance / DuranceStatusView / DuranceConveneView.
// ---------------------------------------------------------------------------

export type DuranceStatus = components['schemas']['DuranceStatus'];
export type DuranceUnlockGate = components['schemas']['DuranceUnlockGate'];
export type DuranceEligiblePath = components['schemas']['DuranceEligiblePath'];
export type DuranceIntent = components['schemas']['DuranceIntent'];
export type DuranceConveneResponse = components['schemas']['DuranceConveneResponse'];

export interface XPData {
  total_earned: number;
  total_spent: number;
  current_available: number;
}

export interface KudosData {
  total_earned: number;
  total_claimed: number;
  current_available: number;
}

export interface XPTransaction {
  id: number;
  amount: number;
  reason_display: string;
  description: string;
  character_name: string | null;
  transaction_date: string;
}

export interface KudosTransaction {
  id: number;
  amount: number;
  source_category_name: string | null;
  claim_category_name: string | null;
  description: string;
  transaction_date: string;
}

export interface KudosClaimCategory {
  id: number;
  name: string;
  display_name: string;
  description: string;
  kudos_cost: number;
  reward_amount: number;
}

export interface AccountProgressionData {
  xp: XPData | null;
  kudos: KudosData | null;
  xp_transactions: XPTransaction[];
  kudos_transactions: KudosTransaction[];
  claim_categories: KudosClaimCategory[];
}
