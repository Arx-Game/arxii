/**
 * CrossoverInboxPage — GM inbox for crossover invites (#2075).
 *
 * Shows incoming invites (received — where from_gm_account !== account.id)
 * and sent invites (where from_gm_account === account.id).
 *
 * The API queryset already filters to invites where from_gm__account == user OR
 * to_story.owners == user, so all returned invites are relevant to the viewer.
 * The frontend partitions by comparing from_gm_account against the account ID.
 *
 * Route: /crossover/inbox (ProtectedRoute).
 */

import { useMemo } from 'react';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import { Skeleton } from '@/components/ui/skeleton';
import { useAccount } from '@/store/hooks';
import { useCrossoverInvites } from '../queries';
import { CrossoverInviteCard } from '../components/CrossoverInviteCard';
import type { CrossoverInvite } from '../types';

export function CrossoverInboxPage() {
  return (
    <ErrorBoundary>
      <CrossoverInboxContent />
    </ErrorBoundary>
  );
}

function CrossoverInboxContent() {
  const account = useAccount();
  const accountId = account?.id ?? null;
  const { data, isLoading, isError, error } = useCrossoverInvites();

  const invites = data?.results ?? [];

  const { incoming, sent } = useMemo(() => {
    const incoming: CrossoverInvite[] = [];
    const sent: CrossoverInvite[] = [];
    for (const invite of invites) {
      if (accountId != null && invite.from_gm_account === accountId) {
        sent.push(invite);
      } else {
        incoming.push(invite);
      }
    }
    // Sort: pending first, then by created_at desc
    const sortBy = (a: CrossoverInvite, b: CrossoverInvite) => {
      if (a.status === 'pending' && b.status !== 'pending') return -1;
      if (a.status !== 'pending' && b.status === 'pending') return 1;
      return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
    };
    incoming.sort(sortBy);
    sent.sort(sortBy);
    return { incoming, sent };
  }, [invites, accountId]);

  if (isLoading) {
    return <Skeleton className="h-96 w-full" />;
  }

  if (isError) {
    return (
      <div className="p-8 text-center text-destructive">
        Failed to load crossover invites: {(error as Error)?.message}
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6">
      <h1 className="text-2xl font-bold">Crossover Inbox</h1>

      {/* Incoming */}
      <section>
        <h2 className="mb-3 text-lg font-semibold">Incoming Invites ({incoming.length})</h2>
        {incoming.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No incoming crossover invites. When a GM invites your story to co-run an event, it will
            appear here.
          </p>
        ) : (
          <div className="space-y-3">
            {incoming.map((invite) => (
              <CrossoverInviteCard
                key={invite.id}
                invite={invite}
                isSent={false}
                storyTitle={`Story #${invite.to_story}`}
                eventTitle={`Event #${invite.event}`}
              />
            ))}
          </div>
        )}
      </section>

      {/* Sent */}
      <section>
        <h2 className="mb-3 text-lg font-semibold">Sent Invites ({sent.length})</h2>
        {sent.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            No sent crossover invites. Visit a story page to send a crossover invite.
          </p>
        ) : (
          <div className="space-y-3">
            {sent.map((invite) => (
              <CrossoverInviteCard
                key={invite.id}
                invite={invite}
                isSent={true}
                storyTitle={`Story #${invite.to_story}`}
                eventTitle={`Event #${invite.event}`}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
