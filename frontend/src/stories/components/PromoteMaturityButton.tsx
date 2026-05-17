/**
 * PromoteMaturityButton — Task E3
 *
 * Minimal-functional episode maturity promotion control. Shows the current
 * maturity and a single button that promotes the episode to the next rung
 * (pitch → outline → plot). At plot the control is a disabled "Plot (max)".
 *
 * The B1 promote endpoint returns 400 with body `{ "target": "<message>" }`
 * when a PLOT promotion fails the maturity gate (needs a resting conclusion
 * and either an outbound transition or an explicit ending). The design wants
 * that message surfaced INLINE so the GM sees exactly why it failed — not a
 * transient toast. We mirror the DRF-400-surfacing mechanism used by
 * BeatFormDialog / MarkBeatDialog: the apiFetch error object carries the
 * failed `Response`; `response.json()` resolves to the DRF error body, which
 * we read and render inline.
 *
 * Success relies on the hook's query invalidation (usePromoteEpisode
 * invalidates the episode + episode list + story caches); no manual refetch.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { Button } from '@/components/ui/button';
import { usePromoteEpisode } from '../queries';
import type { EpisodeMaturity } from '../types';

// ---------------------------------------------------------------------------
// DRF error shape — the promote action 400s with { target: "<message>" }.
// `target` may also arrive as string[] for standard DRF field errors; we
// normalise both.
// ---------------------------------------------------------------------------

interface PromoteDRFError {
  target?: string | string[];
  non_field_errors?: string[];
  detail?: string;
}

// ---------------------------------------------------------------------------
// Maturity ladder
// ---------------------------------------------------------------------------

const MATURITY_ORDER: EpisodeMaturity[] = ['pitch', 'outline', 'plot'];

function nextMaturity(current: EpisodeMaturity): EpisodeMaturity | null {
  const idx = MATURITY_ORDER.indexOf(current);
  if (idx === -1 || idx >= MATURITY_ORDER.length - 1) return null;
  return MATURITY_ORDER[idx + 1];
}

function capitalize(value: string): string {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

/** Minimum episode shape needed to promote: id + current maturity. */
export interface PromotableEpisode {
  id: number;
  maturity: EpisodeMaturity;
}

interface PromoteMaturityButtonProps {
  episode: PromotableEpisode;
  storyId: number;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function PromoteMaturityButton({ episode, storyId }: PromoteMaturityButtonProps) {
  const [inlineError, setInlineError] = useState<string>('');
  const promoteMutation = usePromoteEpisode();

  const target = nextMaturity(episode.maturity);
  const atMax = target === null;

  function handleError(err: unknown) {
    if (err && typeof err === 'object' && 'response' in err) {
      const response = (err as { response?: Response }).response;
      if (response) {
        void response
          .json()
          .then((data: unknown) => {
            if (data && typeof data === 'object') {
              const body = data as PromoteDRFError;
              const targetErr = Array.isArray(body.target) ? body.target.join(' ') : body.target;
              const message =
                targetErr ||
                body.non_field_errors?.join(' ') ||
                body.detail ||
                'Promotion failed. Please try again.';
              setInlineError(message);
            } else {
              setInlineError('Promotion failed. Please try again.');
            }
          })
          .catch(() => setInlineError('Promotion failed. Please try again.'));
        return;
      }
    }
    setInlineError(err instanceof Error ? err.message : 'Promotion failed. Please try again.');
  }

  function handlePromote() {
    if (target === null) return;
    // Clear any prior gate error before the new attempt.
    setInlineError('');
    promoteMutation.mutate(
      { episodeId: episode.id, storyId, target },
      {
        onSuccess: () => {
          setInlineError('');
          toast.success(`Episode promoted to ${capitalize(target)}`);
        },
        onError: handleError,
      }
    );
  }

  return (
    <div className="flex flex-col items-start gap-1">
      <div className="flex items-center gap-2">
        <span
          data-testid="promote-maturity-current"
          className="inline-flex w-fit items-center rounded-md border bg-muted px-2 py-1 text-xs text-muted-foreground"
        >
          Maturity: <span className="ml-1 font-medium capitalize">{episode.maturity}</span>
        </span>
        {atMax ? (
          <Button type="button" variant="outline" size="sm" disabled>
            Plot (max)
          </Button>
        ) : (
          <Button
            type="button"
            variant="outline"
            size="sm"
            onClick={handlePromote}
            disabled={promoteMutation.isPending}
          >
            {promoteMutation.isPending ? 'Promoting…' : `Promote to ${capitalize(target)}`}
          </Button>
        )}
      </div>
      {inlineError && (
        <p data-testid="promote-maturity-error" className="text-xs text-destructive">
          {inlineError}
        </p>
      )}
    </div>
  );
}
