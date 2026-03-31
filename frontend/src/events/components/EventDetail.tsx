import { useMutation, useQueryClient } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Lock, MapPin, Pencil, User } from 'lucide-react';
import { toast } from 'sonner';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
  AlertDialogTrigger,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Separator } from '@/components/ui/separator';
import { urls } from '@/utils/urls';
import { EventInvitations } from './EventInvitations';
import { EventStatusBadge } from './EventStatusBadge';
import { TimePhaseBadge } from './TimePhaseBadge';
import { eventLifecycleAction } from '../queries';
import { EVENT_STATUS } from '../types';
import type { EventDetailData } from '../types';

interface EventDetailProps {
  event: EventDetailData;
  isHost?: boolean;
  isStaff?: boolean;
  isGM?: boolean;
}

export function EventDetail({
  event,
  isHost = false,
  isStaff = false,
  isGM = false,
}: EventDetailProps) {
  const queryClient = useQueryClient();
  const canManageLifecycle = isHost || isStaff;
  const canEndEvent = canManageLifecycle || isGM;
  const isEditable = event.status === EVENT_STATUS.DRAFT || event.status === EVENT_STATUS.SCHEDULED;

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

      {/* Invitations */}
      <EventInvitations event={event} canManage={canManageLifecycle && isEditable} />

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
      <div className="flex flex-wrap gap-2">
        {canManageLifecycle &&
          (event.status === EVENT_STATUS.DRAFT || event.status === EVENT_STATUS.SCHEDULED) && (
            <Button variant="outline" asChild>
              <Link to={urls.eventEdit(event.id)}>
                <Pencil className="mr-1 h-4 w-4" />
                Edit
              </Link>
            </Button>
          )}
        {canManageLifecycle && event.status === EVENT_STATUS.DRAFT && (
          <>
            <Button
              onClick={() => lifecycleMutation.mutate('schedule')}
              disabled={lifecycleMutation.isPending}
            >
              Schedule
            </Button>
            <Button
              variant="ghost"
              onClick={() => lifecycleMutation.mutate('cancel')}
              disabled={lifecycleMutation.isPending}
            >
              Cancel
            </Button>
          </>
        )}
        {canManageLifecycle && event.status === EVENT_STATUS.SCHEDULED && (
          <>
            <Button
              onClick={() => lifecycleMutation.mutate('start')}
              disabled={lifecycleMutation.isPending}
            >
              Start Event
            </Button>
            <AlertDialog>
              <AlertDialogTrigger asChild>
                <Button variant="destructive" disabled={lifecycleMutation.isPending}>
                  Cancel Event
                </Button>
              </AlertDialogTrigger>
              <AlertDialogContent>
                <AlertDialogHeader>
                  <AlertDialogTitle>Cancel this event?</AlertDialogTitle>
                  <AlertDialogDescription>
                    This cannot be undone. The event will be marked as cancelled and removed from
                    upcoming listings.
                  </AlertDialogDescription>
                </AlertDialogHeader>
                <AlertDialogFooter>
                  <AlertDialogCancel>Go Back</AlertDialogCancel>
                  <AlertDialogAction
                    className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                    onClick={() => lifecycleMutation.mutate('cancel')}
                  >
                    Cancel Event
                  </AlertDialogAction>
                </AlertDialogFooter>
              </AlertDialogContent>
            </AlertDialog>
          </>
        )}
        {canEndEvent && event.status === EVENT_STATUS.ACTIVE && (
          <AlertDialog>
            <AlertDialogTrigger asChild>
              <Button variant="destructive" disabled={lifecycleMutation.isPending}>
                End Event
              </Button>
            </AlertDialogTrigger>
            <AlertDialogContent>
              <AlertDialogHeader>
                <AlertDialogTitle>End this event?</AlertDialogTitle>
                <AlertDialogDescription>
                  This will end the event and its scene for all participants.
                </AlertDialogDescription>
              </AlertDialogHeader>
              <AlertDialogFooter>
                <AlertDialogCancel>Go Back</AlertDialogCancel>
                <AlertDialogAction
                  className="bg-destructive text-destructive-foreground hover:bg-destructive/90"
                  onClick={() => lifecycleMutation.mutate('complete')}
                >
                  End Event
                </AlertDialogAction>
              </AlertDialogFooter>
            </AlertDialogContent>
          </AlertDialog>
        )}
      </div>
    </div>
  );
}
