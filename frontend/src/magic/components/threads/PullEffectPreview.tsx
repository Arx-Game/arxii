/**
 * PullEffectPreview — single-thread pull preview for the Thread Detail page.
 *
 * - Tier 1/2/3 radio selector
 * - Debounced preview call (250ms) via api.previewPull on every tier change
 * - Shows cost (resonance + anima), affordability flag, capped_intensity warning
 * - Lists resolved_effects with kind/scaled_value/inactive_reason
 * - [Pull Now (RP)] button opens ThreadPullDialog in ephemeral mode (always-in-action anchors)
 *
 * Always-in-action (non-combat) anchor kinds: if a thread's anchor is NOT in
 * this set, the pull button is disabled with a tooltip.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import { previewPull } from '../../api';
import type { PreviewedEffect, PullPreviewResponse, Thread } from '../../types';
import { ThreadPullDialog } from './ThreadPullDialog';

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

/** Anchor kinds that are always in action (non-combat context is fine). */
const ALWAYS_IN_ACTION_KINDS = new Set([
  'RELATIONSHIP_TRACK',
  'RELATIONSHIP_CAPSTONE',
  'FACET',
  'COVENANT_ROLE',
]);

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function tierLabel(tier: 1 | 2 | 3): string {
  return `Tier ${tier}`;
}

interface EffectRowProps {
  effect: PreviewedEffect;
}

function EffectRow({ effect }: EffectRowProps) {
  return (
    <li
      className={`flex flex-col gap-0.5 rounded px-2 py-1.5 text-xs ${
        effect.inactive ? 'opacity-50' : 'bg-muted'
      }`}
      data-testid={`effect-row-${effect.kind}`}
    >
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium">{effect.kind.replace(/_/g, ' ')}</span>
        <span className="tabular-nums">{effect.scaled_value}</span>
      </div>
      {effect.inactive && effect.inactive_reason && (
        <p className="text-muted-foreground" data-testid="effect-inactive-reason">
          {effect.inactive_reason}
        </p>
      )}
      {effect.narrative_snippet && (
        <p className="italic text-muted-foreground">{effect.narrative_snippet}</p>
      )}
    </li>
  );
}

// ---------------------------------------------------------------------------
// Main component
// ---------------------------------------------------------------------------

interface PullEffectPreviewProps {
  thread: Thread;
}

export function PullEffectPreview({ thread }: PullEffectPreviewProps) {
  const [tier, setTier] = useState<1 | 2 | 3>(1);
  const [preview, setPreview] = useState<PullPreviewResponse | null>(null);
  const [loadingPreview, setLoadingPreview] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [pullDialogOpen, setPullDialogOpen] = useState(false);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const isAlwaysInAction = ALWAYS_IN_ACTION_KINDS.has(thread.target_kind);

  const fetchPreview = useCallback(
    (selectedTier: 1 | 2 | 3) => {
      setLoadingPreview(true);
      setPreviewError(null);

      previewPull({
        character_sheet_id: thread.owner,
        resonance_id: thread.resonance,
        tier: selectedTier,
        thread_ids: [thread.id],
      })
        .then((result) => {
          setPreview(result);
          setLoadingPreview(false);
        })
        .catch((err: unknown) => {
          setPreviewError(err instanceof Error ? err.message : 'Failed to load preview.');
          setLoadingPreview(false);
        });
    },
    [thread.id, thread.owner, thread.resonance]
  );

  // Debounced fetch on tier change.
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(() => {
      fetchPreview(tier);
    }, 250);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [tier, fetchPreview]);

  return (
    <div className="space-y-4 rounded-lg border p-4" data-testid="pull-effect-preview">
      <h3 className="text-sm font-semibold">Pull Preview</h3>

      {/* Tier selector */}
      <div className="flex gap-2" role="group" aria-label="Tier selector">
        {([1, 2, 3] as const).map((t) => (
          <button
            key={t}
            type="button"
            role="radio"
            aria-checked={tier === t}
            onClick={() => setTier(t)}
            className={`rounded-md border px-3 py-1 text-sm font-medium transition-colors ${
              tier === t
                ? 'border-primary bg-primary text-primary-foreground'
                : 'border-border bg-background hover:bg-muted'
            }`}
            data-testid={`tier-radio-${t}`}
          >
            {tierLabel(t)}
          </button>
        ))}
      </div>

      {/* Preview results */}
      {loadingPreview && (
        <p className="text-sm text-muted-foreground" data-testid="preview-loading">
          Loading preview…
        </p>
      )}

      {previewError && (
        <p className="text-sm text-destructive" data-testid="preview-error" role="alert">
          {previewError}
        </p>
      )}

      {preview && !loadingPreview && (
        <div className="space-y-3">
          {/* Cost summary */}
          <div className="flex flex-wrap gap-x-4 gap-y-1 text-sm" data-testid="preview-costs">
            <span>
              Resonance cost:{' '}
              <span className="font-medium tabular-nums">{preview.resonance_cost}</span>
            </span>
            <span>
              Anima cost: <span className="font-medium tabular-nums">{preview.anima_cost}</span>
            </span>
            {!preview.affordable && (
              <span className="font-medium text-destructive" data-testid="preview-unaffordable">
                Insufficient resources
              </span>
            )}
          </div>

          {/* Capped intensity warning */}
          {preview.capped_intensity && (
            <p
              className="text-sm text-yellow-700 dark:text-yellow-400"
              data-testid="preview-capped-intensity"
            >
              Intensity has been capped by thread level or tier constraints.
            </p>
          )}

          {/* Effects list */}
          {preview.resolved_effects.length > 0 && (
            <ul className="space-y-1" data-testid="preview-effects-list">
              {preview.resolved_effects.map((effect, idx) => (
                // Effect rows may repeat kinds (e.g. multiple FLAT_BONUS rows for different threads),
                // so we key by index.
                <EffectRow key={idx} effect={effect} />
              ))}
            </ul>
          )}
        </div>
      )}

      {/* Pull Now — opens ThreadPullDialog in ephemeral mode */}
      <div className="flex items-center gap-3">
        <Button
          type="button"
          disabled={!isAlwaysInAction}
          data-testid="pull-now-button"
          title={!isAlwaysInAction ? 'Requires combat context' : undefined}
          onClick={() => setPullDialogOpen(true)}
        >
          Pull Now (RP)
        </Button>
        {!isAlwaysInAction && (
          <span className="text-xs text-muted-foreground" data-testid="pull-combat-context-note">
            Requires combat context
          </span>
        )}
      </div>

      <ThreadPullDialog
        characterSheetId={thread.owner}
        open={pullDialogOpen}
        onClose={() => setPullDialogOpen(false)}
      />
    </div>
  );
}
