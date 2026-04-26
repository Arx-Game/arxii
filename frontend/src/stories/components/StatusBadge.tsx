/**
 * Status badge for story episode status values.
 * Colors are based on the StoryEpisodeStatus semantics.
 */

import { Badge } from '@/components/ui/badge';
import { cn } from '@/lib/utils';

// Status values come from StoryEpisodeStatus in the backend.
// We use a string type here because the backend sends these as string labels.
type EpisodeStatus = string;

const STATUS_CLASSES: Record<string, string> = {
  waiting_on_beats: 'bg-amber-600 text-white border-transparent',
  ready_to_resolve: 'bg-green-600 text-white border-transparent',
  scheduled: 'bg-blue-600 text-white border-transparent',
  completed: 'bg-gray-500 text-white border-transparent',
  stalled: 'bg-red-600 text-white border-transparent',
};

function getStatusClass(status: EpisodeStatus): string {
  return STATUS_CLASSES[status] ?? 'bg-secondary text-secondary-foreground border-transparent';
}

interface StatusBadgeProps {
  status: EpisodeStatus;
  label: string;
  className?: string;
}

export function StatusBadge({ status, label, className }: StatusBadgeProps) {
  return <Badge className={cn(getStatusClass(status), className)}>{label}</Badge>;
}
