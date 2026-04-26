/**
 * AssignedSessionRequestRow — single row for an assigned session request in GMQueuePage.
 *
 * Read-only for Wave 5. Action UIs (schedule, cancel, resolve) come in Wave 6.
 */

import { Link } from 'react-router-dom';
import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import type { GMQueueAssignedRequest } from '../types';

interface AssignedSessionRequestRowProps {
  request: GMQueueAssignedRequest;
}

const STATUS_CLASSES: Record<string, string> = {
  open: 'bg-amber-600 text-white border-transparent',
  scheduled: 'bg-blue-600 text-white border-transparent',
  resolved: 'bg-gray-500 text-white border-transparent',
  cancelled: 'bg-red-600 text-white border-transparent',
};

function statusClass(status: string): string {
  return STATUS_CLASSES[status] ?? 'bg-secondary text-secondary-foreground border-transparent';
}

export function AssignedSessionRequestRow({ request }: AssignedSessionRequestRowProps) {
  return (
    <Card data-testid="assigned-session-request-row">
      <CardContent className="py-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="text-base font-semibold">{request.story_title}</span>
          <Badge className={statusClass(request.status)}>{request.status.toUpperCase()}</Badge>
        </div>

        <p className="mt-1 text-sm text-muted-foreground">{request.episode_title}</p>

        {request.event_id !== null && (
          <div className="mt-2">
            <Link
              to={`/events/${request.event_id}`}
              className="text-sm font-medium text-primary underline-offset-4 hover:underline"
            >
              View event
            </Link>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
