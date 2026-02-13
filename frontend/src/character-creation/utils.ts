import type { ApplicationStatus } from './types';

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
