/**
 * ThreadPullDialog — thread pull selector (select-only surface).
 *
 * Calls `onSelect` with the chosen tier/threads so the caller
 * (e.g. combat cast dispatch or clash commit) can include the pull inline
 * in its own request. Pull no longer commits standalone — it rides
 * cast/clash everywhere.
 *
 * Ephemeral mode (no `combat` prop): only ALWAYS_IN_ACTION_KINDS are eligible.
 * Combat mode (`combat` prop set): TRAIT/TECHNIQUE threads additionally
 * eligible when their anchor appears in the involved-ID lists.
 *
 * The threads may be of different resonances; each is paid from its own (#5066), so
 * there is no resonance to pick first. A thread whose resonance has no balance is not
 * offered.
 *
 * Live preview: every change debounces a previewPull call (250ms).
 */

import { useCallback, useEffect, useRef, useState } from 'react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  NO_DESCRIPTION,
} from '@/components/ui/dialog';
import { previewPull } from '../../api';
import { pulledResonances } from '../../burn';
import { useCharacterResonances, useThreads } from '../../queries';
import type { PullPreviewResponse, Thread } from '../../types';

// ---------------------------------------------------------------------------
// Pull selection shape — returned via onSelect in combat / inline mode.
// ---------------------------------------------------------------------------

export interface PullSelection {
  tier: 1 | 2 | 3;
  thread_ids: number[];
  /** The distinct resonances of the chosen threads (a burn picks one when several). */
  resonances: { id: number; name: string }[];
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

const ALWAYS_IN_ACTION_KINDS = new Set([
  'RELATIONSHIP_TRACK',
  'RELATIONSHIP_CAPSTONE',
  'FACET',
  'COVENANT_ROLE',
]);

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

export interface ThreadPullDialogProps {
  characterSheetId: number;
  open: boolean;
  onClose: () => void;
  /** Combat mode: provided by the combat declaration panel.
   *  involvedTraitIds / involvedTechniqueIds unlock TRAIT/TECHNIQUE threads
   *  whose anchor PK is in the respective set.
   *  Leave undefined for ephemeral (non-combat) pulls. */
  combat?: {
    encounterId: number;
    participantId: number;
    involvedTraitIds: number[];
    involvedTechniqueIds: number[];
  };
  /**
   * Called with the chosen pull parameters when the player confirms their
   * selection. The caller (e.g. combat cast/clash dispatch) includes these as
   * kwargs in its own dispatch request — the pull rides the action, not a
   * standalone commit endpoint. The dialog closes after calling onSelect.
   */
  onSelect: (selection: PullSelection) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isThreadEligible(thread: Thread, combat: ThreadPullDialogProps['combat']): boolean {
  if (ALWAYS_IN_ACTION_KINDS.has(thread.target_kind)) return true;
  if (!combat) return false;
  if (thread.target_kind === 'TECHNIQUE' && thread.target_technique_id != null) {
    return combat.involvedTechniqueIds.includes(thread.target_technique_id);
  }
  if (thread.target_kind === 'TRAIT' && thread.target_trait_id != null) {
    return combat.involvedTraitIds.includes(thread.target_trait_id);
  }
  return false;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function ThreadPullDialog({
  characterSheetId,
  open,
  onClose,
  combat,
  onSelect,
}: ThreadPullDialogProps) {
  const { data: allThreads } = useThreads();
  const { data: resonances } = useCharacterResonances(characterSheetId);

  const [selectedTier, setSelectedTier] = useState<1 | 2 | 3>(1);
  const [selectedThreadIds, setSelectedThreadIds] = useState<number[]>([]);
  const [preview, setPreview] = useState<PullPreviewResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Reset state when dialog opens.
  useEffect(() => {
    if (open) {
      setSelectedTier(1);
      setSelectedThreadIds([]);
      setPreview(null);
      setPreviewLoading(false);
      setPreviewError(null);
    }
  }, [open]);

  // Eligible non-retired threads.
  const eligibleThreads = (allThreads?.results ?? []).filter(
    (t) => t.retired_at == null && isThreadEligible(t, combat)
  );

  // A thread is offered when its resonance has a balance to pay from.
  const balanceOf = new Map((resonances ?? []).map((r) => [r.resonance, r.balance ?? 0]));
  const offeredThreads = eligibleThreads.filter((t) => (balanceOf.get(t.resonance) ?? 0) > 0);

  // Debounced live preview.
  const runPreview = useCallback(() => {
    if (selectedThreadIds.length === 0) {
      setPreview(null);
      setPreviewLoading(false);
      return;
    }
    setPreviewLoading(true);
    setPreviewError(null);
    previewPull({
      character_sheet_id: characterSheetId,
      tier: selectedTier,
      thread_ids: selectedThreadIds,
    })
      .then((result) => {
        setPreview(result);
        setPreviewLoading(false);
      })
      .catch((err: unknown) => {
        setPreviewError(err instanceof Error ? err.message : 'Failed to load preview.');
        setPreviewLoading(false);
      });
  }, [characterSheetId, selectedTier, selectedThreadIds]);

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(runPreview, 250);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [runPreview]);

  function toggleThread(threadId: number) {
    setSelectedThreadIds((prev) =>
      prev.includes(threadId) ? prev.filter((id) => id !== threadId) : [...prev, threadId]
    );
  }

  function handleSelect() {
    if (selectedThreadIds.length === 0) return;
    onSelect({
      tier: selectedTier,
      thread_ids: selectedThreadIds,
      resonances: pulledResonances(offeredThreads.filter((t) => selectedThreadIds.includes(t.id))),
    });
    onClose();
  }

  const canSelect = selectedThreadIds.length > 0 && (preview?.affordable ?? false);

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent {...NO_DESCRIPTION} className="max-w-lg" data-testid="thread-pull-dialog">
        <DialogHeader>
          <DialogTitle>Pull Threads</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Tier selector */}
          <div className="space-y-1">
            <span
              id="pull-tier-label"
              className="text-xs font-semibold uppercase tracking-wide text-muted-foreground"
            >
              Tier
            </span>
            <div className="flex gap-2" role="radiogroup" aria-labelledby="pull-tier-label">
              {([1, 2, 3] as const).map((t) => (
                <button
                  key={t}
                  type="button"
                  role="radio"
                  aria-checked={selectedTier === t}
                  onClick={() => setSelectedTier(t)}
                  data-testid={`tier-btn-${t}`}
                  className={`rounded-md border px-3 py-1 text-sm font-medium transition-colors ${
                    selectedTier === t
                      ? 'border-primary bg-primary text-primary-foreground'
                      : 'border-border bg-background hover:bg-muted'
                  }`}
                >
                  Tier {t}
                </button>
              ))}
            </div>
          </div>

          {/* Thread checkboxes: any resonances, each paid from its own */}
          <fieldset className="space-y-1">
            <legend className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Threads
            </legend>
            <div className="space-y-1.5" data-testid="thread-checklist">
              {offeredThreads.length === 0 && (
                <p className="text-sm text-muted-foreground">No threads to pull.</p>
              )}
              {offeredThreads.map((thread) => {
                const checked = selectedThreadIds.includes(thread.id);
                return (
                  <label
                    key={thread.id}
                    className="flex cursor-pointer items-center gap-2 rounded border border-border bg-card/60 px-3 py-2 text-sm hover:bg-muted"
                    data-testid={`thread-checkbox-${thread.id}`}
                  >
                    <input
                      type="checkbox"
                      checked={checked}
                      onChange={() => toggleThread(thread.id)}
                      className="accent-primary"
                    />
                    <span>{thread.name || `Thread #${thread.id}`}</span>
                    <span className="ml-auto text-xs text-muted-foreground">
                      {thread.resonance_name}{' '}
                      <span className="tabular-nums">{balanceOf.get(thread.resonance)}</span>
                    </span>
                  </label>
                );
              })}
            </div>
          </fieldset>

          {/* Live preview */}
          {previewLoading && (
            <p className="text-sm text-muted-foreground" data-testid="preview-loading">
              Loading preview…
            </p>
          )}
          {previewError && (
            <p className="text-sm text-destructive" role="alert" data-testid="preview-error">
              {previewError}
            </p>
          )}
          {preview && !previewLoading && (
            <div
              className="space-y-2 rounded-lg border bg-muted/30 p-3 text-sm"
              data-testid="preview-panel"
            >
              <div className="flex flex-wrap gap-x-4 gap-y-1">
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
              {preview.capped_intensity && (
                <p className="text-yellow-700 dark:text-yellow-400">
                  Intensity has been capped by thread level or tier constraints.
                </p>
              )}
              {preview.resolved_effects.length > 0 && (
                <ul className="space-y-1">
                  {preview.resolved_effects.map((effect, i) => (
                    <li
                      key={i}
                      className={`flex items-center justify-between rounded px-2 py-1 text-xs ${
                        effect.inactive ? 'opacity-50' : 'bg-background'
                      }`}
                    >
                      <span>{effect.kind.replace(/_/g, ' ')}</span>
                      <span className="tabular-nums">{effect.scaled_value}</span>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button onClick={handleSelect} disabled={!canSelect} data-testid="commit-pull-btn">
            Select Pull
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
