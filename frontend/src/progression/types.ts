/**
 * Types for progression data (XP and Kudos).
 */

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
  awarded_by_name: string | null;
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
