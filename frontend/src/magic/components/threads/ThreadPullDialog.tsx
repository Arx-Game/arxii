/**
 * ThreadPullDialog — multi-thread pull commit surface.
 *
 * Ephemeral mode (no `combat` prop): only ALWAYS_IN_ACTION_KINDS are eligible.
 * Combat mode (`combat` prop set): TRAIT/TECHNIQUE/ROOM threads additionally
 * eligible when their anchor appears in the involved-ID lists.
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
} from '@/components/ui/dialog';
import { previewPull } from '../../api';
import { useCharacterResonances, useCommitPull, useThreads } from '../../queries';
import type { PullPreviewResponse, Thread } from '../../types';

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
   *  involvedTraitIds / involvedTechniqueIds / involvedObjectIds unlock
   *  TRAIT/TECHNIQUE/ROOM threads whose anchor PK is in the respective set.
   *  Leave undefined for ephemeral (non-combat) pulls. */
  combat?: {
    encounterId: number;
    participantId: number;
    involvedTraitIds: number[];
    involvedTechniqueIds: number[];
    involvedObjectIds: number[];
  };
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function isThreadEligible(thread: Thread, combat: ThreadPullDialogProps['combat']): boolean {
  if (ALWAYS_IN_ACTION_KINDS.has(thread.target_kind)) return true;
  if (!combat) return false;
  // For TRAIT/TECHNIQUE/ROOM eligibility in combat we'd check thread.target_id
  // against the involved lists — target_id is not in the Thread response shape
  // (write-only field), so v1 leaves these disabled until target_id is exposed.
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
}: ThreadPullDialogProps) {
  const { data: allThreads } = useThreads();
  const { data: resonances } = useCharacterResonances(characterSheetId);
  const { mutate: commitPull, isPending: committing } = useCommitPull();

  const [selectedResonanceId, setSelectedResonanceId] = useState<number | null>(null);
  const [selectedTier, setSelectedTier] = useState<1 | 2 | 3>(1);
  const [selectedThreadIds, setSelectedThreadIds] = useState<number[]>([]);
  const [preview, setPreview] = useState<PullPreviewResponse | null>(null);
  const [previewLoading, setPreviewLoading] = useState(false);
  const [previewError, setPreviewError] = useState<string | null>(null);
  const [commitError, setCommitError] = useState<string | null>(null);

  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Reset state when dialog opens.
  useEffect(() => {
    if (open) {
      setSelectedResonanceId(null);
      setSelectedTier(1);
      setSelectedThreadIds([]);
      setPreview(null);
      setPreviewLoading(false);
      setPreviewError(null);
      setCommitError(null);
    }
  }, [open]);

  // Eligible non-retired threads.
  const eligibleThreads = (allThreads?.results ?? []).filter(
    (t) => t.retired_at == null && isThreadEligible(t, combat)
  );

  // Resonances that have ≥1 eligible thread and balance > 0.
  const eligibleResonanceIds = new Set(eligibleThreads.map((t) => t.resonance));
  const selectableResonances = (resonances ?? []).filter(
    (r) => eligibleResonanceIds.has(r.resonance) && (r.balance ?? 0) > 0
  );

  // Threads filtered to the selected resonance.
  const threadsForResonance = selectedResonanceId
    ? eligibleThreads.filter((t) => t.resonance === selectedResonanceId)
    : [];

  // Debounced live preview.
  const runPreview = useCallback(() => {
    if (selectedResonanceId === null || selectedThreadIds.length === 0) {
      setPreview(null);
      setPreviewLoading(false);
      return;
    }
    setPreviewLoading(true);
    setPreviewError(null);
    previewPull({
      character_sheet_id: characterSheetId,
      resonance_id: selectedResonanceId,
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
  }, [characterSheetId, selectedResonanceId, selectedTier, selectedThreadIds]);

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

  function handleCommit() {
    if (selectedResonanceId === null || selectedThreadIds.length === 0) return;
    setCommitError(null);
    commitPull(
      {
        character_sheet_id: characterSheetId,
        resonance_id: selectedResonanceId,
        tier: selectedTier,
        thread_ids: selectedThreadIds,
      },
      {
        onSuccess: () => onClose(),
        onError: (err: unknown) => {
          setCommitError(err instanceof Error ? err.message : 'Could not commit pull.');
        },
      }
    );
  }

  const canCommit =
    selectedResonanceId !== null &&
    selectedThreadIds.length > 0 &&
    (preview?.affordable ?? false) &&
    !committing;

  return (
    <Dialog open={open} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-lg" data-testid="thread-pull-dialog">
        <DialogHeader>
          <DialogTitle>Pull Threads</DialogTitle>
        </DialogHeader>

        <div className="space-y-4 py-2">
          {/* Resonance selector */}
          <div className="space-y-1">
            <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Resonance
            </label>
            <div className="flex flex-wrap gap-2" data-testid="resonance-selector">
              {selectableResonances.length === 0 && (
                <p className="text-sm text-muted-foreground">
                  No eligible resonances with balance.
                </p>
              )}
              {selectableResonances.map((r) => (
                <button
                  key={r.resonance}
                  type="button"
                  onClick={() => {
                    setSelectedResonanceId(r.resonance);
                    setSelectedThreadIds([]);
                    setPreview(null);
                  }}
                  data-testid={`resonance-btn-${r.resonance}`}
                  className={`rounded-md border px-3 py-1 text-sm font-medium transition-colors ${
                    selectedResonanceId === r.resonance
                      ? 'border-primary bg-primary text-primary-foreground'
                      : 'border-border bg-background hover:bg-muted'
                  }`}
                >
                  {r.resonance_name ?? `Resonance ${r.resonance}`}
                  <span className="ml-1.5 text-xs tabular-nums opacity-70">{r.balance}</span>
                </button>
              ))}
            </div>
          </div>

          {/* Tier selector */}
          <div className="space-y-1">
            <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
              Tier
            </label>
            <div className="flex gap-2" role="group" aria-label="Tier selector">
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

          {/* Thread checkboxes */}
          {selectedResonanceId !== null && (
            <div className="space-y-1">
              <label className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                Threads
              </label>
              <div className="space-y-1.5" data-testid="thread-checklist">
                {threadsForResonance.length === 0 && (
                  <p className="text-sm text-muted-foreground">
                    No eligible threads for this resonance.
                  </p>
                )}
                {threadsForResonance.map((thread) => {
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
                        {thread.target_kind}
                      </span>
                    </label>
                  );
                })}
              </div>
            </div>
          )}

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

          {/* Commit error */}
          {commitError && (
            <p className="text-sm text-destructive" role="alert" data-testid="commit-error">
              {commitError}
            </p>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose} disabled={committing}>
            Cancel
          </Button>
          <Button onClick={handleCommit} disabled={!canCommit} data-testid="commit-pull-btn">
            {committing ? 'Committing…' : 'Commit Pull'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
