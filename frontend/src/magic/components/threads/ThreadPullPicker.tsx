/**
 * ThreadPullPicker — contextual thread-pull selection widget.
 *
 * Per spec §5 of docs/superpowers/specs/2026-05-23-unified-combat-ui-design.md.
 *
 * Layout:
 *   - Header: "Thread pulls — N applicable" + small counts
 *   - Toolbar: name-search input + "Show inapplicable" toggle
 *   - Scroll body: applicable rows first, then divider + inapplicable rows
 *   - Footnote: auto-revert behavior note
 *
 * Data flow:
 *   - useApplicablePulls(actionContext) → which threads are applicable
 *   - useThreads() → full thread list for names/anchors/levels
 *   - For each applicable row with a paid tier selected, debounced previewPull call
 *
 * Auto-revert: when actionContext changes, drops paid pulls whose threads are
 * no longer applicable, and surfaces a notice via onAutoRevertNotice if provided.
 */

import { lazy, Suspense, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { cn } from '@/lib/utils';
import { useApplicablePulls, useThreads } from '@/magic/queries';
import { previewPull } from '@/magic/api';
import type {
  ApplicablePullsRequest,
  PullPreviewResponse,
  Thread,
  ThreadApplicability,
} from '@/magic/types';

// Lazy-load PullDetailModal to avoid build-time import ordering issues when
// both files live in the same directory and each references the other.
const PullDetailModal = lazy(() =>
  import('./PullDetailModal').then((m) => ({ default: m.PullDetailModal }))
);

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type TierValue = 0 | 1 | 2 | 3;

export interface ThreadPullPickerProps {
  characterSheetId: number;
  actionContext: ApplicablePullsRequest;
  selectedPulls: Record<number, TierValue>;
  onPullsChange: (next: Record<number, TierValue>) => void;
  showInapplicable: boolean;
  onToggleInapplicable: (next: boolean) => void;
  onAutoRevertNotice?: (msg: string) => void;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function anchorDescription(thread: Thread): string {
  const kind = thread.target_kind.replace(/_/g, ' ');
  return `${kind} · ${thread.resonance_name}`;
}

// ---------------------------------------------------------------------------
// Per-row preview hook (debounced, manual)
// ---------------------------------------------------------------------------

interface RowPreviewState {
  preview: PullPreviewResponse | null;
  loading: boolean;
}

function useRowPreview(
  thread: Thread,
  tier: TierValue,
  characterSheetId: number
): RowPreviewState {
  const [state, setState] = useState<RowPreviewState>({ preview: null, loading: false });
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    // Tier 0 is always-on passive — no cost preview needed.
    if (tier === 0) {
      setState({ preview: null, loading: false });
      return;
    }

    setState((prev) => ({ ...prev, loading: true }));
    if (debounceRef.current) clearTimeout(debounceRef.current);

    debounceRef.current = setTimeout(() => {
      previewPull({
        character_sheet_id: characterSheetId,
        resonance_id: thread.resonance,
        tier,
        thread_ids: [thread.id],
      })
        .then((result) => setState({ preview: result, loading: false }))
        .catch(() => setState({ preview: null, loading: false }));
    }, 250);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [thread.id, thread.resonance, tier, characterSheetId]);

  return state;
}

// ---------------------------------------------------------------------------
// Tier strip sub-component
// ---------------------------------------------------------------------------

interface TierStripProps {
  threadId: number;
  selectedTier: TierValue;
  onSelectTier: (tier: TierValue) => void;
  preview: PullPreviewResponse | null;
  previewLoading: boolean;
}

function TierStrip({
  threadId,
  selectedTier,
  onSelectTier,
  preview,
  previewLoading,
}: TierStripProps) {
  const tiers: TierValue[] = [0, 1, 2, 3];

  return (
    <div
      className="flex items-center gap-1.5"
      role="group"
      aria-label={`Tier selection for thread ${threadId}`}
    >
      <span className="text-xs text-muted-foreground mr-1">Tier</span>
      {tiers.map((tier) => {
        const isSelected = selectedTier === tier;
        const isTier0 = tier === 0;
        const isUnaffordable =
          tier > 0 && isSelected && preview !== null && !preview.affordable;

        const tooltipText = isTier0
          ? 'Always-on passive (no cost)'
          : isUnaffordable
          ? 'Insufficient resources for this tier'
          : previewLoading && isSelected
          ? 'Loading affordability…'
          : undefined;

        return (
          <button
            key={tier}
            type="button"
            onClick={() => onSelectTier(tier)}
            title={tooltipText}
            data-testid={`tier-btn-${threadId}-${tier}`}
            className={cn(
              'rounded border px-2 py-0.5 text-xs font-medium transition-colors min-w-[28px]',
              isTier0 && isSelected
                ? 'border-emerald-500/60 bg-emerald-500/20 text-emerald-300'
                : isSelected && !isUnaffordable
                ? 'border-primary bg-primary/10 text-primary'
                : isSelected && isUnaffordable
                ? 'border-muted bg-muted/30 text-muted-foreground opacity-60'
                : 'border-border bg-background text-muted-foreground hover:border-primary/40 hover:text-foreground'
            )}
          >
            {String(tier)}
          </button>
        );
      })}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Applicable row
// ---------------------------------------------------------------------------

interface ApplicableRowProps {
  thread: Thread;
  selectedTier: TierValue;
  onSelectTier: (tier: TierValue) => void;
  characterSheetId: number;
  onOpenDetails: (thread: Thread) => void;
}

function ApplicableRow({
  thread,
  selectedTier,
  onSelectTier,
  characterSheetId,
  onOpenDetails,
}: ApplicableRowProps) {
  const { preview, loading: previewLoading } = useRowPreview(
    thread,
    selectedTier,
    characterSheetId
  );
  const hasPaidTier = selectedTier > 0;

  return (
    <div
      className="rounded-md border border-border bg-card p-3 space-y-2"
      data-testid={`applicable-row-${thread.id}`}
    >
      {/* Head */}
      <div>
        <p className="text-sm font-semibold text-foreground">
          {thread.name || `Thread #${thread.id}`}
        </p>
        <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
          {anchorDescription(thread)}
        </p>
      </div>

      {/* Tier strip */}
      <TierStrip
        threadId={thread.id}
        selectedTier={selectedTier}
        onSelectTier={onSelectTier}
        preview={preview}
        previewLoading={previewLoading}
      />

      {/* Active line */}
      {selectedTier === 0 && (
        <p className="text-xs text-emerald-300/80">Passive: always-on (tier 0)</p>
      )}
      {selectedTier > 0 && previewLoading && (
        <p className="text-xs text-muted-foreground">Loading preview…</p>
      )}
      {selectedTier > 0 && !previewLoading && preview && (
        <p className="text-xs text-muted-foreground">
          {preview.resolved_effects.length > 0
            ? `Pulled: ${preview.resolved_effects[0].kind.replace(/_/g, ' ')} (×${preview.resolved_effects[0].scaled_value})`
            : 'No active effects at this tier'}
        </p>
      )}

      {/* Cost line — only when paid tier selected */}
      {hasPaidTier && !previewLoading && preview && (
        <div className="flex items-center gap-2">
          <p className="text-xs text-amber-400">
            {`−${preview.resonance_cost} resonance · −${preview.anima_cost} anima`}
          </p>
          <button
            type="button"
            onClick={() => onOpenDetails(thread)}
            className="text-xs text-primary/80 hover:text-primary transition-colors"
            data-testid={`details-btn-${thread.id}`}
          >
            ▸ details
          </button>
        </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Inapplicable row
// ---------------------------------------------------------------------------

interface InapplicableRowProps {
  thread: Thread;
  applicabilityRow: ThreadApplicability;
}

function InapplicableRow({ thread, applicabilityRow }: InapplicableRowProps) {
  return (
    <div
      className="rounded-md border border-dashed border-border/50 bg-card/40 p-3 space-y-2 opacity-60"
      data-testid={`inapplicable-row-${thread.id}`}
    >
      {/* Head */}
      <div>
        <p className="text-sm font-semibold text-foreground">
          {thread.name || `Thread #${thread.id}`}
        </p>
        <p className="text-[10px] uppercase tracking-wide text-muted-foreground">
          {anchorDescription(thread)}
        </p>
      </div>

      {/* Reason chip */}
      {applicabilityRow.inapplicable_reason && (
        <span
          className="inline-block rounded border border-border/50 bg-muted/40 px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground"
          data-testid={`inapplicable-reason-chip-${thread.id}`}
        >
          {applicabilityRow.inapplicable_reason.replace(/_/g, ' ')}
        </span>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ThreadPullPicker
// ---------------------------------------------------------------------------

export function ThreadPullPicker({
  characterSheetId,
  actionContext,
  selectedPulls,
  onPullsChange,
  showInapplicable,
  onToggleInapplicable,
  onAutoRevertNotice,
}: ThreadPullPickerProps) {
  const [nameFilter, setNameFilter] = useState('');
  const [detailThread, setDetailThread] = useState<Thread | null>(null);

  const { data: applicableData, isLoading: applicableLoading } = useApplicablePulls(actionContext);
  const { data: threadsData, isLoading: threadsLoading } = useThreads();

  // Build lookup: thread_id → Thread
  const threadById = useMemo<Map<number, Thread>>(() => {
    const threads = threadsData?.results ?? [];
    return new Map(threads.map((t) => [t.id, t]));
  }, [threadsData]);

  // Partition into applicable/inapplicable
  const applicableIds = useMemo<number[]>(() => {
    if (!applicableData) return [];
    return applicableData.filter((r) => r.applicable).map((r) => r.thread_id);
  }, [applicableData]);

  const inapplicableRows = useMemo<ThreadApplicability[]>(() => {
    if (!applicableData) return [];
    return applicableData.filter((r) => !r.applicable);
  }, [applicableData]);

  // Filter by name
  const filteredApplicable = useMemo<Thread[]>(() => {
    const filter = nameFilter.toLowerCase();
    return applicableIds
      .map((id) => threadById.get(id))
      .filter((t): t is Thread => t !== undefined)
      .filter((t) => !filter || (t.name || '').toLowerCase().includes(filter));
  }, [applicableIds, threadById, nameFilter]);

  const filteredInapplicable = useMemo<Array<{ thread: Thread; row: ThreadApplicability }>>(() => {
    const filter = nameFilter.toLowerCase();
    return inapplicableRows
      .map((row) => ({ row, thread: threadById.get(row.thread_id) }))
      .filter((x): x is { thread: Thread; row: ThreadApplicability } => x.thread !== undefined)
      .filter(({ thread }) => !filter || (thread.name || '').toLowerCase().includes(filter));
  }, [inapplicableRows, threadById, nameFilter]);

  // Set of currently-applicable thread IDs (for auto-revert)
  const applicableSet = useMemo(() => new Set(applicableIds), [applicableIds]);

  // Auto-revert: when applicableData changes, drop paid pulls that are no longer applicable.
  // Runs only when applicableData changes (i.e. after the query resolves for a new context).
  useEffect(() => {
    if (!applicableData) return;

    const next: Record<number, TierValue> = {};
    let reverted = 0;
    const revertedNames: string[] = [];

    for (const [tidStr, tier] of Object.entries(selectedPulls)) {
      const tid = Number(tidStr);
      if (tier === 0 || applicableSet.has(tid)) {
        next[tid] = tier;
      } else {
        reverted++;
        const thread = threadById.get(tid);
        revertedNames.push(thread?.name ?? `Thread #${tid}`);
      }
    }

    if (reverted > 0) {
      onPullsChange(next);
      if (onAutoRevertNotice) {
        const names = revertedNames.join(', ');
        onAutoRevertNotice(
          `${reverted} pull${reverted > 1 ? 's' : ''} (${names}) reverted to tier 0 — no longer applicable.`
        );
      }
    }
    // Intentionally omitting selectedPulls and onPullsChange from deps to avoid
    // re-running on every selection change. This effect should only fire when
    // the applicability data itself changes (new context).
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [applicableData]);

  const handleSelectTier = useCallback(
    (threadId: number, tier: TierValue) => {
      onPullsChange({ ...selectedPulls, [threadId]: tier });
    },
    [selectedPulls, onPullsChange]
  );

  const handleOpenDetails = useCallback((thread: Thread) => {
    setDetailThread(thread);
  }, []);

  const handleCloseDetails = useCallback(() => {
    setDetailThread(null);
  }, []);

  const isLoading = applicableLoading || threadsLoading;
  const applicableCount = applicableIds.length;
  const pulledCount = Object.values(selectedPulls).filter((t) => t > 0).length;
  const passiveCount = Object.values(selectedPulls).filter((t) => t === 0).length;

  return (
    <div className="space-y-3" data-testid="thread-pull-picker">
      {/* Header */}
      <div className="flex items-center justify-between">
        <h4 className="text-sm font-semibold text-foreground">
          Thread pulls{' '}
          <span className="font-normal text-muted-foreground text-xs">
            — {isLoading ? '…' : `${applicableCount} applicable`}
          </span>
        </h4>
        {(pulledCount > 0 || passiveCount > 0) && (
          <p className="text-xs text-muted-foreground">
            {pulledCount > 0 && `${pulledCount} pulled`}
            {pulledCount > 0 && passiveCount > 0 && ' · '}
            {passiveCount > 0 && `${passiveCount} passive`}
          </p>
        )}
      </div>

      {/* Toolbar */}
      <div className="flex items-center gap-2">
        <input
          type="text"
          placeholder="Filter by name…"
          value={nameFilter}
          onChange={(e) => setNameFilter(e.target.value)}
          className={cn(
            'flex-1 rounded border border-border bg-background px-2 py-1 text-xs text-foreground',
            'placeholder:text-muted-foreground focus:outline-none focus:ring-1 focus:ring-ring'
          )}
          data-testid="thread-name-filter"
        />
        <label className="flex items-center gap-1.5 cursor-pointer select-none">
          <input
            type="checkbox"
            checked={showInapplicable}
            onChange={(e) => onToggleInapplicable(e.target.checked)}
            className="h-3.5 w-3.5 rounded border-border accent-primary"
            data-testid="show-inapplicable-toggle"
          />
          <span className="text-xs text-muted-foreground">Show inapplicable</span>
        </label>
      </div>

      {/* Applicable rows */}
      {isLoading ? (
        <p className="text-xs text-muted-foreground">Loading threads…</p>
      ) : filteredApplicable.length === 0 ? (
        <p className="text-xs text-muted-foreground italic" data-testid="no-applicable-threads">
          No applicable threads.
        </p>
      ) : (
        <div className="space-y-2" data-testid="applicable-rows">
          {filteredApplicable.map((thread) => (
            <ApplicableRow
              key={thread.id}
              thread={thread}
              selectedTier={selectedPulls[thread.id] ?? 0}
              onSelectTier={(tier) => handleSelectTier(thread.id, tier)}
              characterSheetId={characterSheetId}
              onOpenDetails={handleOpenDetails}
            />
          ))}
        </div>
      )}

      {/* Inapplicable rows — under a divider when toggled */}
      {showInapplicable && filteredInapplicable.length > 0 && (
        <>
          <div className="flex items-center gap-2">
            <div className="flex-1 border-t border-border/50" />
            <span className="text-[10px] uppercase tracking-wide text-muted-foreground">
              Inapplicable
            </span>
            <div className="flex-1 border-t border-border/50" />
          </div>
          <div className="space-y-2" data-testid="inapplicable-rows">
            {filteredInapplicable.map(({ thread, row }) => (
              <InapplicableRow key={thread.id} thread={thread} applicabilityRow={row} />
            ))}
          </div>
        </>
      )}

      {/* Footnote */}
      <p className="text-[10px] text-muted-foreground/70">
        Changing your focused action may revert paid pulls that no longer apply.
      </p>

      {/* Detail modal */}
      {detailThread !== null && (
        <Suspense fallback={null}>
          <PullDetailModal
            thread={detailThread}
            open={true}
            onOpenChange={(open) => {
              if (!open) handleCloseDetails();
            }}
          />
        </Suspense>
      )}
    </div>
  );
}
