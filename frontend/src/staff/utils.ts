import type { InboxItem, SubmissionStatus } from '@/staff/types';

export function detailPath(item: InboxItem): string {
  switch (item.source_type) {
    case 'player_feedback':
      return `/staff/feedback/${item.source_pk}`;
    case 'bug_report':
      return `/staff/bug-reports/${item.source_pk}`;
    case 'player_report':
      return `/staff/player-reports/${item.source_pk}`;
    case 'character_application':
      return `/staff/applications/${item.source_pk}`;
  }
}

export function statusVariant(status: string): 'default' | 'secondary' | 'outline' {
  switch (status) {
    case 'open':
      return 'default';
    case 'reviewed':
      return 'secondary';
    case 'dismissed':
      return 'outline';
    default:
      return 'outline';
  }
}

export const STATUS_OPTIONS: { label: string; value: SubmissionStatus | undefined }[] = [
  { label: 'All', value: undefined },
  { label: 'Open', value: 'open' },
  { label: 'Reviewed', value: 'reviewed' },
  { label: 'Dismissed', value: 'dismissed' },
];
