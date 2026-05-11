/**
 * RitualSessionInboxPage — list of pending ritual session invitations.
 *
 * Polls every 5 s via useRitualSessionInbox(). Clicking "Respond" on a row
 * opens RitualSessionResponseDialog for that session.
 *
 * The dialog needs the full RitualSessionDetail, so clicking "Respond" navigates
 * to the session detail page instead of opening an inline dialog — the detail
 * page holds the full session data and hosts the response dialog there.
 * This avoids a second detail fetch just for the inline dialog.
 */

import { useNavigate } from 'react-router-dom';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Skeleton } from '@/components/ui/skeleton';
import { Button } from '@/components/ui/button';
import { useRitualSessionInbox } from '@/rituals/queries';
import type { RitualSessionList } from '../api';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function formatRelativeTime(isoDate: string): string {
  const ms = new Date(isoDate).getTime() - Date.now();
  const minutes = Math.round(ms / 60_000);
  if (minutes < 0) return 'expired';
  if (minutes < 60) return `${minutes}m`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.round(hours / 24)}d`;
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function InboxRowSkeleton() {
  return (
    <div className="animate-pulse rounded-lg border bg-card p-4" data-testid="inbox-row-skeleton">
      <div className="flex items-center justify-between gap-4">
        <div className="flex-1 space-y-2">
          <Skeleton className="h-5 w-48" />
          <Skeleton className="h-4 w-full" />
        </div>
        <Skeleton className="h-8 w-20 shrink-0" />
      </div>
    </div>
  );
}

function LoadingSkeletons() {
  return (
    <div className="space-y-3">
      {[0, 1, 2].map((i) => (
        <InboxRowSkeleton key={i} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inbox row
// ---------------------------------------------------------------------------

interface InboxRowProps {
  session: RitualSessionList;
}

function InboxRow({ session }: InboxRowProps) {
  const navigate = useNavigate();

  return (
    <div
      className="flex items-center justify-between gap-4 rounded-lg border bg-card p-4"
      data-testid="inbox-row"
    >
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <span className="font-medium text-foreground">{session.ritual_name}</span>
          <span className="text-xs text-muted-foreground">
            — expires {formatRelativeTime(session.expires_at)}
          </span>
        </div>
        <p className="mt-1 text-sm text-muted-foreground">
          <span className="font-medium">{session.initiator_name}</span> invites you.
          {session.proposed_terms ? ` "${session.proposed_terms}"` : ''}
        </p>
      </div>
      <Button
        size="sm"
        onClick={() => {
          navigate(`/rituals/sessions/${session.id}`);
        }}
      >
        Respond
      </Button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inner page (inside error boundary)
// ---------------------------------------------------------------------------

function RitualSessionInboxInner() {
  const { data, isLoading } = useRitualSessionInbox();

  if (isLoading) return <LoadingSkeletons />;

  const sessions = data ?? [];

  if (sessions.length === 0) {
    return (
      <p className="py-8 text-center text-muted-foreground" data-testid="inbox-empty">
        No pending invitations.
      </p>
    );
  }

  return (
    <div className="space-y-3" data-testid="inbox-list">
      {sessions.map((session) => (
        <InboxRow key={session.id} session={session} />
      ))}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page export
// ---------------------------------------------------------------------------

export function RitualSessionInboxPage() {
  return (
    <div className="container mx-auto px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
      <h1 className="mb-6 text-2xl font-bold">Ritual Invitations</h1>
      <ErrorBoundary>
        <RitualSessionInboxInner />
      </ErrorBoundary>
    </div>
  );
}
