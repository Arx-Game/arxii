import { Badge } from '@/components/ui/badge';
import type { EventStatus } from '../types';

const STATUS_CONFIG: Record<EventStatus, { label: string; className: string }> = {
  draft: { label: 'Draft', className: 'bg-gray-100 text-gray-700 border-gray-300' },
  scheduled: { label: 'Scheduled', className: 'bg-blue-100 text-blue-700 border-blue-300' },
  active: { label: 'Active', className: 'bg-green-100 text-green-700 border-green-300' },
  completed: { label: 'Completed', className: 'bg-muted text-muted-foreground' },
  cancelled: { label: 'Cancelled', className: 'bg-red-100 text-red-700 border-red-300' },
};

interface EventStatusBadgeProps {
  status: EventStatus;
}

export function EventStatusBadge({ status }: EventStatusBadgeProps) {
  const config = STATUS_CONFIG[status];
  return (
    <Badge variant="outline" className={config.className}>
      {config.label}
    </Badge>
  );
}
