/**
 * PrecaptureConsentNotifier — site-wide alert for a pending pre-scene capture consent
 * ask (#3069 sub-item 4): "a scene would like to fold in your recent unattached poses."
 *
 * Mirrors `DuelChallengeNotifier` (#2157) — mounted once at the app root, polls an
 * account-wide inbox, fires one `toast.custom()` per newly-seen pending request id with
 * inline Accept/Decline buttons, dedupes via a ref `Set`.
 *
 * Simpler than `DuelChallengeNotifier`/`ConsentAttentionNotifier`: the consent decision
 * is ACCOUNT-level, not persona/character-targeted (`PrecaptureConsentRequest.account`
 * is the interaction's pinned `writer_account` — the same player regardless of which
 * face wrote the pose), so there is no character-session resolution or switch-then-
 * navigate step. Accept/decline post straight to the account-scoped endpoint and
 * dismiss the toast on success.
 *
 * Renders nothing itself — `null` always, purely a side-effect component.
 */

import { useEffect, useRef, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import { fetchPendingPrecaptureConsents, respondToPrecaptureConsent } from '../precaptureQueries';
import type { PrecaptureConsentRequest } from '../types';

interface ToastBodyProps {
  toastId: string | number;
  request: PrecaptureConsentRequest;
  onResolved: () => void;
}

function PrecaptureConsentToastBody({ toastId, request, onResolved }: ToastBodyProps) {
  const [isPending, setIsPending] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handle(accept: boolean) {
    setIsPending(true);
    setError(null);
    try {
      await respondToPrecaptureConsent(request.id, accept);
      onResolved();
      toast.dismiss(toastId);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to respond');
    } finally {
      setIsPending(false);
    }
  }

  const count = request.candidates.length;
  const plural = count === 1 ? '' : 's';
  const room = request.room_name ?? 'somewhere';

  return (
    <div
      className="rounded-md border border-amber-500/50 bg-amber-500/10 p-3 shadow-sm"
      data-testid="precapture-consent-toast"
    >
      <p className="text-sm text-foreground">
        A scene at <span className="font-semibold">{room}</span> would like to fold in{' '}
        <span className="font-semibold">
          {count} of your recent pose{plural}
        </span>{' '}
        from before it started.
      </p>
      <div className="mt-2 flex gap-2">
        <button
          type="button"
          disabled={isPending}
          onClick={() => {
            handle(true).catch(() => {});
          }}
          data-testid="precapture-toast-accept-btn"
          className="rounded border border-emerald-500/60 bg-emerald-500/10 px-3 py-1 text-xs font-semibold text-emerald-300 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isPending ? 'Sending…' : 'Include them'}
        </button>
        <button
          type="button"
          disabled={isPending}
          onClick={() => {
            handle(false).catch(() => {});
          }}
          data-testid="precapture-toast-decline-btn"
          className="rounded border border-destructive/60 bg-destructive/10 px-3 py-1 text-xs font-semibold text-destructive disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isPending ? 'Sending…' : 'Leave them out'}
        </button>
      </div>
      {error !== null && (
        <p
          role="alert"
          className="mt-2 text-xs text-destructive"
          data-testid="precapture-toast-error"
        >
          {error}
        </p>
      )}
    </div>
  );
}

export function PrecaptureConsentNotifier() {
  const queryClient = useQueryClient();
  const { data: pendingRequests = [] } = useQuery({
    queryKey: ['precapture-consent-requests'],
    queryFn: fetchPendingPrecaptureConsents,
    refetchInterval: 15_000,
    staleTime: 10_000,
  });

  const toastedIds = useRef<Set<number>>(new Set());

  useEffect(() => {
    for (const request of pendingRequests) {
      if (toastedIds.current.has(request.id)) continue;
      toastedIds.current.add(request.id);

      toast.custom((toastId) => (
        <PrecaptureConsentToastBody
          toastId={toastId}
          request={request}
          onResolved={() => {
            queryClient.invalidateQueries({ queryKey: ['precapture-consent-requests'] });
          }}
        />
      ));
    }
  }, [pendingRequests, queryClient]);

  return null;
}
