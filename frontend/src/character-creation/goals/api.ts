import { apiFetch } from '@/evennia_replacements/api';
import type { GoalDomain } from './types';

/**
 * Fetch all goal domains.
 */
export async function fetchGoalDomains(): Promise<GoalDomain[]> {
  const response = await apiFetch('/api/goals/domains/');
  if (!response.ok) {
    throw new Error('Failed to fetch goal domains');
  }
  return response.json();
}
