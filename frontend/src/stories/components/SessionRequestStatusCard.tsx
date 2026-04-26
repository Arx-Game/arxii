/**
 * SessionRequestStatusCard — player-facing session request status display.
 *
 * Wave 4 task 4.2: read-only/status-display path.
 *
 * All SessionRequest update actions (create-event, cancel, resolve) are
 * gated behind IsSessionRequestGMOrStaff — there is no player-callable
 * update endpoint.  This component therefore surfaces the current status
 * so the player knows what is happening, without providing any controls.
 *
 * Deferred (Wave 6 / GM action UIs): GM scheduling controls.
 */

import { useSessionRequest } from '../queries';
import type { MyActiveStoryEntry } from '../types';

interface SessionRequestStatusCardProps {
  activeEntry: MyActiveStoryEntry;
}

export function SessionRequestStatusCard({ activeEntry }: SessionRequestStatusCardProps) {
  const { open_session_request_id, scheduled_event_id, scheduled_real_time } = activeEntry;

  // Fetch the session request details when we have an ID, so we can show
  // the status string rather than just "pending".
  // Always call unconditionally to satisfy Rules of Hooks — enabled: false when no id.
  const requestId = open_session_request_id ?? 0;
  const { data: sessionRequest } = useSessionRequest(requestId);

  // If neither an open session request nor a scheduled event exists,
  // show nothing — the episode is progressing through beats.
  if (!open_session_request_id && !scheduled_event_id) {
    return null;
  }

  // Scheduled event path — session has been run.
  if (scheduled_event_id) {
    return (
      <div className="rounded-lg border bg-card p-4">
        <h3 className="text-sm font-semibold">Session</h3>
        {scheduled_real_time ? (
          <p className="mt-1 text-sm text-foreground">
            Scheduled for{' '}
            {new Date(scheduled_real_time).toLocaleString(undefined, {
              dateStyle: 'medium',
              timeStyle: 'short',
            })}
          </p>
        ) : (
          <p className="mt-1 text-sm text-foreground">Session has been scheduled.</p>
        )}
        <p className="mt-1 text-xs text-muted-foreground">
          Your GM will run this session. Watch for an event invite.
        </p>
      </div>
    );
  }

  // Open session request path — GM has been notified.
  const statusLabel =
    sessionRequest?.status === 'open'
      ? 'Session pending — your GM has been notified'
      : sessionRequest?.status === 'scheduled'
        ? 'Session scheduled — your GM is finalising the event'
        : sessionRequest?.status === 'resolved'
          ? 'Session resolved'
          : 'Episode ready — GM scheduling required';

  return (
    <div className="rounded-lg border bg-card p-4">
      <h3 className="text-sm font-semibold">Session Status</h3>
      <p className="mt-1 text-sm text-foreground">{statusLabel}</p>
      <p className="mt-1 text-xs text-muted-foreground">
        No action needed on your part right now. Your GM will reach out to schedule a session.
      </p>
    </div>
  );
}
