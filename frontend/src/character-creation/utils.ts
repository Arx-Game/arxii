import type { RealmTheme } from '@/components/realm-theme-provider';

import type { ApplicationStatus, StartingArea } from './types';

// =============================================================================
// Realm Theme Mapping
// =============================================================================

const VALID_REALM_THEMES: RealmTheme[] = [
  'default',
  'arx',
  'umbros',
  'luxen',
  'inferna',
  'ariwn',
  'aythirmok',
];

function isRealmTheme(value: string): value is RealmTheme {
  return (VALID_REALM_THEMES as string[]).includes(value);
}

/** Get the realm theme from a starting area's backend data. Returns 'default' for unknown themes. */
export function getRealmTheme(area: StartingArea): RealmTheme {
  const theme = area.realm_theme;
  if (isRealmTheme(theme)) return theme;
  return 'default';
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
