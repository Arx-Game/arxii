import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Lock, MapPin, User, Users } from 'lucide-react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { EventStatusBadge } from './EventStatusBadge';
import { TimePhaseBadge } from './TimePhaseBadge';
import { eventLifecycleAction } from '../queries';
import { EVENT_STATUS } from '../types';
import type { EventDetailData } from '../types';

interface EventDetailProps {
  event: EventDetailData;
  isHost?: boolean;
  isStaff?: boolean;
}

export function EventDetail({ event, isHost = false, isStaff = false }: EventDetailProps) {
  const queryClient = useQueryClient();
  const canManage = isHost || isStaff;

  const lifecycleMutation = useMutation({
    mutationFn: (action: 'schedule' | 'start' | 'complete' | 'cancel') =>
      eventLifecycleAction(event.id, action),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['event', String(event.id)] });
      queryClient.invalidateQueries({ queryKey: ['events'] });
    },
    onError: (err: Error) => {
      toast.error(err.message);
    },
  });

  const dateStr = new Date(event.scheduled_real_time).toLocaleString(undefined, {
    weekday: 'long',
    month: 'long',
    day: 'numeric',
    year: 'numeric',
    hour: 'numeric',
    minute: '2-digit',
  });

  const icDateStr = event.scheduled_ic_time
    ? new Date(event.scheduled_ic_time).toLocaleString(undefined, {
        month: 'long',
        day: 'numeric',
        year: 'numeric',
      })
    : null;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div>
        <div className="flex items-center gap-3">
          <h1 className="text-2xl font-bold">{event.name}</h1>
          <EventStatusBadge status={event.status} />
          {!event.is_public && <Lock className="h-4 w-4 text-muted-foreground" />}
        </div>
        {event.description && <p className="mt-2 text-muted-foreground">{event.description}</p>}
      </div>

      <Separator />

      {/* Info */}
      <div className="grid gap-4 sm:grid-cols-2">
        <div className="space-y-3">
          <div className="flex items-center gap-2 text-sm">
            <MapPin className="h-4 w-4 text-muted-foreground" />
            <span>{event.location_name}</span>
          </div>
          <div className="text-sm">
            <div className="font-medium">{dateStr}</div>
            {icDateStr && <div className="text-muted-foreground">IC: {icDateStr}</div>}
          </div>
          <TimePhaseBadge phase={event.time_phase} showLabel />
        </div>

        <div className="space-y-3">
          <div className="text-sm">
            <span className="font-medium">{event.hosts.length === 1 ? 'Host' : 'Hosts'}:</span>
            <ul className="mt-1">
              {event.hosts.map((host) => (
                <li key={host.id} className="flex items-center gap-1">
                  <User className="h-3 w-3 text-muted-foreground" />
                  <span>
                    {host.persona_name || '(unknown)'}
                    {host.is_primary && (
                      <span className="ml-1 text-xs text-muted-foreground">(primary)</span>
                    )}
                  </span>
                </li>
              ))}
            </ul>
          </div>
        </div>
      </div>

      {/* Invitations - hosts/staff only */}
      {canManage && event.invitations.length > 0 && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center gap-2 text-base">
              <Users className="h-4 w-4" />
              Invitations ({event.invitations.length})
            </CardTitle>
          </CardHeader>
          <CardContent>
            <ul className="space-y-1 text-sm">
              {event.invitations.map((inv) => (
                <li key={inv.id} className="flex items-center gap-2">
                  <span className="rounded bg-muted px-1.5 py-0.5 text-xs capitalize">
                    {inv.target_type}
                  </span>
                  <span>{inv.target_name || '(deleted)'}</span>
                </li>
              ))}
            </ul>
          </CardContent>
        </Card>
      )}

      {/* Room modification */}
      {event.modification?.room_description_overlay && (
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="text-base">Room Description Overlay</CardTitle>
          </CardHeader>
          <CardContent>
            <p className="text-sm italic">{event.modification.room_description_overlay}</p>
          </CardContent>
        </Card>
      )}

      {/* Host actions */}
      {canManage && (
        <div className="flex flex-wrap gap-2">
          {event.status === EVENT_STATUS.DRAFT && (
            <Button
              onClick={() => lifecycleMutation.mutate('schedule')}
              disabled={lifecycleMutation.isPending}
            >
              Schedule
            </Button>
          )}
          {event.status === EVENT_STATUS.SCHEDULED && (
            <>
              <Button
                onClick={() => lifecycleMutation.mutate('start')}
                disabled={lifecycleMutation.isPending}
              >
                Start Event
              </Button>
              <Button
                variant="destructive"
                onClick={() => lifecycleMutation.mutate('cancel')}
                disabled={lifecycleMutation.isPending}
              >
                Cancel Event
              </Button>
            </>
          )}
          {event.status === EVENT_STATUS.ACTIVE && (
            <>
              <Button
                onClick={() => lifecycleMutation.mutate('complete')}
                disabled={lifecycleMutation.isPending}
              >
                Complete Event
              </Button>
              <Button
                variant="destructive"
                onClick={() => lifecycleMutation.mutate('cancel')}
                disabled={lifecycleMutation.isPending}
              >
                Cancel Event
              </Button>
            </>
          )}
        </div>
      )}
    </div>
  );
}
