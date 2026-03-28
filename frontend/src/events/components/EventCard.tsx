import { Link } from 'react-router-dom';
import { Lock, MapPin, User } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { urls } from '@/utils/urls';
import { EventStatusBadge } from './EventStatusBadge';
import { TimePhaseBadge } from './TimePhaseBadge';
import type { EventListItem } from '../types';

interface EventCardProps {
  event: EventListItem;
  compact?: boolean;
}

export function EventCard({ event, compact = false }: EventCardProps) {
  const dateStr = new Date(event.scheduled_real_time).toLocaleDateString(undefined, {
    weekday: compact ? undefined : 'short',
    month: 'short',
    day: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });

  const icDateStr = event.scheduled_ic_time
    ? new Date(event.scheduled_ic_time).toLocaleDateString(undefined, {
        month: 'short',
        day: 'numeric',
        year: 'numeric',
      })
    : null;

  const nameLink = compact ? (
    <a
      href={urls.event(event.id)}
      target="_blank"
      rel="noopener noreferrer"
      className="font-medium hover:underline"
    >
      {event.name}
    </a>
  ) : (
    <Link to={urls.event(event.id)} className="font-medium hover:underline">
      {event.name}
    </Link>
  );

  if (compact) {
    return (
      <div className="border-b px-3 py-2 last:border-b-0">
        <div className="flex items-center justify-between gap-2">
          <div className="min-w-0 flex-1">
            <div className="truncate">{nameLink}</div>
            <div className="flex items-center gap-2 text-xs text-muted-foreground">
              <span>{dateStr}</span>
              <TimePhaseBadge phase={event.time_phase} />
            </div>
          </div>
          <EventStatusBadge status={event.status} />
        </div>
        {event.primary_host_name && (
          <div className="mt-1 flex items-center gap-1 text-xs text-muted-foreground">
            <User className="h-3 w-3" />
            <span>{event.primary_host_name}</span>
          </div>
        )}
      </div>
    );
  }

  return (
    <Card>
      <CardContent className="p-4">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0 flex-1">
            <div className="flex items-center gap-2">
              {nameLink}
              {!event.is_public && <Lock className="h-3 w-3 text-muted-foreground" />}
            </div>
            {event.description && (
              <p className="mt-1 line-clamp-2 text-sm text-muted-foreground">{event.description}</p>
            )}
            <div className="mt-2 flex flex-wrap items-center gap-3 text-sm text-muted-foreground">
              <span title={icDateStr ? `IC: ${icDateStr}` : undefined}>{dateStr}</span>
              <TimePhaseBadge phase={event.time_phase} showLabel />
              <span className="flex items-center gap-1">
                <MapPin className="h-3 w-3" />
                {event.location_name}
              </span>
              {event.primary_host_name && (
                <span className="flex items-center gap-1">
                  <User className="h-3 w-3" />
                  {event.primary_host_name}
                </span>
              )}
            </div>
          </div>
          <EventStatusBadge status={event.status} />
        </div>
      </CardContent>
    </Card>
  );
}
