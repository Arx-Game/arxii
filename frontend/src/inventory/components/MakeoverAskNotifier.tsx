/**
 * MakeoverAskNotifier — the site-wide toast for a makeover ask addressed to any of the
 * account's characters (#4187). Mounted once at the app root beside
 * `PrecaptureConsentNotifier`, whose poll-and-dedupe shape this copies: the ask is a
 * yes/no about your own body, so the toast itself answers it (Grant / Decline), with the
 * two one-motion shortcuts the social consent prompt already has (always / never).
 */
import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { useAccount } from '@/store/hooks';
import {
  MAKEOVER_REQUESTS_QUERY_KEY,
  fetchPendingMakeoverRequests,
  respondToMakeoverRequest,
  type MakeoverConsentRequest,
  type MakeoverDecision,
  type MakeoverRemember,
} from '../makeoverRequests';

interface ToastBodyProps {
  toastId: string | number;
  request: MakeoverConsentRequest;
  onResolved: () => void;
}

const primaryButton =
  'rounded border px-3 py-1 text-xs font-semibold disabled:cursor-not-allowed disabled:opacity-50';
const linkButton =
  'text-xs text-muted-foreground underline-offset-2 hover:underline disabled:cursor-not-allowed disabled:opacity-50';

function MakeoverAskToastBody({ toastId, request, onResolved }: ToastBodyProps) {
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function answer(decision: MakeoverDecision, remember: MakeoverRemember | null) {
    setIsPending(true);
    setError(null);
    try {
      await respondToMakeoverRequest(request.id, decision, remember);
      onResolved();
      toast.dismiss(toastId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to answer');
    } finally {
      setIsPending(false);
    }
  }

  const stylist = request.stylist_name;
  return (
    <div
      className="rounded-md border border-amber-500/50 bg-amber-500/10 p-3 shadow-sm"
      data-testid="makeover-ask-toast"
    >
      <p className="text-sm text-foreground">{request.description}</p>
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          disabled={isPending}
          onClick={() => void answer('grant', null)}
          data-testid="makeover-ask-grant"
          className={`${primaryButton} border-emerald-500/60 bg-emerald-500/10 text-emerald-300`}
        >
          {isPending ? 'Sending…' : 'Grant'}
        </button>
        <button
          type="button"
          disabled={isPending}
          onClick={() => void answer('decline', null)}
          data-testid="makeover-ask-decline"
          className={`${primaryButton} border-destructive/60 bg-destructive/10 text-destructive`}
        >
          {isPending ? 'Sending…' : 'Decline'}
        </button>
      </div>
      <div className="mt-2 flex gap-3">
        <button
          type="button"
          disabled={isPending}
          onClick={() => void answer('grant', 'always')}
          data-testid="makeover-ask-always"
          className={linkButton}
        >
          Always let {stylist}
        </button>
        <button
          type="button"
          disabled={isPending}
          onClick={() => void answer('decline', 'never')}
          data-testid="makeover-ask-never"
          className={linkButton}
        >
          Never from {stylist}
        </button>
      </div>
      {error !== null && (
        <p role="alert" className="mt-2 text-xs text-destructive" data-testid="makeover-ask-error">
          {error}
        </p>
      )}
    </div>
  );
}

export function MakeoverAskNotifier() {
  const queryClient = useQueryClient();
  const account = useAccount();
  const { data: pending = [] } = useQuery({
    queryKey: MAKEOVER_REQUESTS_QUERY_KEY,
    queryFn: fetchPendingMakeoverRequests,
    enabled: !!account,
    refetchInterval: 15_000,
    staleTime: 10_000,
  });

  const toastedIds = useRef<Set<number>>(new Set());

  useEffect(() => {
    for (const request of pending) {
      if (toastedIds.current.has(request.id)) continue;
      toastedIds.current.add(request.id);
      toast.custom((toastId) => (
        <MakeoverAskToastBody
          toastId={toastId}
          request={request}
          onResolved={() => {
            void queryClient.invalidateQueries({ queryKey: MAKEOVER_REQUESTS_QUERY_KEY });
          }}
        />
      ));
    }
  }, [pending, queryClient]);

  return null;
}
