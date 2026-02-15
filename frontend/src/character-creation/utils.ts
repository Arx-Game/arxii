import type { RealmTheme } from '@/components/realm-theme-provider';

import type { ApplicationStatus } from './types';

// =============================================================================
// Realm Theme Mapping
// =============================================================================

/** Map starting area names (lowercased) to realm theme identifiers. */
const AREA_THEME_MAP: Record<string, RealmTheme> = {
  arx: 'arx',
  'umbral empire': 'umbros',
  'luxen dominion': 'luxen',
  'grand principality of inferna': 'inferna',
  inferna: 'inferna',
  ariwn: 'ariwn',
  aythirmok: 'aythirmok',
};

/** Get the realm theme for a starting area name. Returns 'default' for unknown areas. */
export function getRealmTheme(areaName: string): RealmTheme {
  return AREA_THEME_MAP[areaName.toLowerCase()] ?? 'default';
}

// =============================================================================
// Application Status Utilities
// =============================================================================

/** Map application status to a human-readable label. */
export function statusLabel(status: ApplicationStatus): string {
  const labels: Record<ApplicationStatus, string> = {
    submitted: 'Submitted',
    in_review: 'In Review',
    revisions_requested: 'Revisions Requested',
    approved: 'Approved',
    denied: 'Denied',
    withdrawn: 'Withdrawn',
  };
  return labels[status];
}

/** Map application status to a Badge variant. */
export function statusVariant(
  status: ApplicationStatus
): 'default' | 'secondary' | 'destructive' | 'outline' {
  switch (status) {
    case 'submitted':
    case 'in_review':
      return 'default';
    case 'revisions_requested':
      return 'outline';
    case 'approved':
      return 'secondary';
    case 'denied':
    case 'withdrawn':
      return 'destructive';
  }
}
