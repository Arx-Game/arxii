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
 *   - For each applicable row, previewPull is called for all 3 paid tiers on
 *     mount (no debounce) so unaffordable tiers can be greyed before the user
 *     clicks them (spec §5).
 *
 * Auto-revert: when actionContext changes, drops paid pulls whose threads are
 * no longer applicable, and surfaces a notice via onAutoRevertNotice if provided.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { cn } from '@/lib/utils';
import { useApplicablePulls, useThreads } from '@/magic/queries';
import { previewPull } from '@/magic/api';
import { PullDetailModal } from './PullDetailModal';
import type {
  ApplicablePullsRequest,
  PullPreviewResponse,
  Thread,
  ThreadApplicability,
} from '@/magic/types';

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

type TierValue = 0 | 1 | 2 | 3;
type PaidTier = 1 | 2 | 3;

export interface ThreadPullPickerProps {
  characterSheetId: number;
  actionContext: ApplicablePullsRequest;
  selectedPulls: Record<number, TierValue>;
  onPullsChange: (next: Record<number, TierValue>) => void;
  showInapplicable: boolean;
  onToggleInapplicable: (next: boolean) => void;
  onAutoRevertNotice?: (msg: string) => void;
  /**
   * Map from resonance_id → current spendable balance.
   * Used by TierStrip to build "Need X Sworn; have Y" tooltips for
   * unaffordable tiers (spec §5).
   */
  balanceByResonanceId?: Record<number, number>;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function anchorDescription(thread: Thread): string {
  const kind = thread.target_kind.replace(/_/g, ' ');
  return `${kind} · ${thread.resonance_name}`;
}

// ---------------------------------------------------------------------------
// Per-row tier-previews hook
//
// Fires previewPull for all three paid tiers (1, 2, 3) on mount — no debounce,
// one-shot per tier — so TierStrip can grey unaffordable tiers before the user
// clicks them (spec §5: "unaffordable tiers are greyed with a tooltip").
//
// An `ignore` flag guards against stale responses: if the effect re-runs (e.g.
// characterSheetId change), the earlier in-flight response is discarded.
// ---------------------------------------------------------------------------

type TierPreviews = Record<PaidTier, PullPreviewResponse | null>;

function useRowTierPreviews(thread: Thread, characterSheetId: number): TierPreviews {
  const [previews, setPreviews] = useState<TierPreviews>({ 1: null, 2: null, 3: null });

  useEffect(() => {
    let ignore = false;

    const PAID_TIERS: PaidTier[] = [1, 2, 3];
    for (const tier of PAID_TIERS) {
      previewPull({
        character_sheet_id: characterSheetId,
        resonance_id: thread.resonance,
        tier,
        thread_ids: [thread.id],
      })
        .then((result) => {
          if (!ignore) {
            setPreviews((prev) => ({ ...prev, [tier]: result }));
          }
        })
        .catch(() => {
          // Leave null on error — tier remains tentatively enabled.
        });
    }

    return () => {
      ignore = true;
    };
  }, [thread.id, thread.resonance, characterSheetId]);

  return previews;
}

// ---------------------------------------------------------------------------
// Tier strip sub-component
// ---------------------------------------------------------------------------

interface TierStripProps {
  threadId: number;
  resonanceId: number;
  resonanceName: string;
  selectedTier: TierValue;
  onSelectTier: (tier: TierValue) => void;
  tierPreviews: TierPreviews;
  balanceByResonanceId: Record<number, number>;
}

function TierStrip({
  threadId,
  resonanceId,
  resonanceName,
  selectedTier,
  onSelectTier,
  tierPreviews,
  balanceByResonanceId,
}: TierStripProps) {
  const tiers: TierValue[] = [0, 1, 2, 3];
  const currentBalance = balanceByResonanceId[resonanceId] ?? 0;

  return (
    <div
      className="flex items-center gap-1.5"
      role="group"
      aria-label={`Tier selection for thread ${threadId}`}
    >
      <span className="mr-1 text-xs text-muted-foreground">Tier</span>
      {tiers.map((tier) => {
        const isSelected = selectedTier === tier;
        const isTier0 = tier === 0;

        // For paid tiers: use the pre-fetched preview to determine affordability.
        // null means preview hasn't resolved yet — leave tentatively enabled.
        const paidPreview = tier > 0 ? tierPreviews[tier as PaidTier] : null;
        const isUnaffordable = paidPreview !== null && !paidPreview.affordable;

        let tooltipText: string | undefined;
        if (isTier0) {
          tooltipText = 'Always-on passive (no cost)';
        } else if (isUnaffordable && paidPreview !== null) {
          tooltipText = `Need ${paidPreview.resonance_cost} ${resonanceName}; have ${currentBalance}`;
        }

        return (
          <button
            key={tier}
            type="button"
            onClick={() => {
              if (!isUnaffordable) onSelectTier(tier);
            }}
            disabled={isUnaffordable}
            title={tooltipText}
            data-testid={`tier-btn-${threadId}-${tier}`}
            className={cn(
              'min-w-[28px] rounded border px-2 py-0.5 text-xs font-medium transition-colors',
              'disabled:cursor-not-allowed',
              isTier0 && isSelected
                ? 'border-emerald-500/60 bg-emerald-500/20 text-emerald-300'
                : isUnaffordable
                  ? 'border-muted bg-muted/30 text-muted-foreground opacity-60'
                  : isSelected
                    ? 'border-primary bg-primary/10 text-primary'
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
  balanceByResonanceId: Record<number, number>;
  onOpenDetails: (thread: Thread) => void;
}

function ApplicableRow({
  thread,
  selectedTier,
  onSelectTier,
  characterSheetId,
  balanceByResonanceId,
  onOpenDetails,
}: ApplicableRowProps) {
  const tierPreviews = useRowTierPreviews(thread, characterSheetId);

  // Use the pre-fetched preview for the selected paid tier.
  const selectedPreview = selectedTier > 0 ? tierPreviews[selectedTier as PaidTier] : null;
  const hasPaidTier = selectedTier > 0;

  return (
    <div
      className="space-y-2 rounded-md border border-border bg-card p-3"
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
        resonanceId={thread.resonance}
        resonanceName={thread.resonance_name}
        selectedTier={selectedTier}
        onSelectTier={onSelectTier}
        tierPreviews={tierPreviews}
        balanceByResonanceId={balanceByResonanceId}
      />

      {/* Active line */}
      {selectedTier === 0 && (
        <p className="text-xs text-emerald-300/80">Passive: always-on (tier 0)</p>
      )}
      {selectedTier > 0 && selectedPreview === null && (
        <p className="text-xs text-muted-foreground">Loading preview…</p>
      )}
      {selectedTier > 0 && selectedPreview !== null && (
        <p className="text-xs text-muted-foreground">
          {selectedPreview.resolved_effects.length > 0
            ? `Pulled: ${selectedPreview.resolved_effects[0].kind.replace(/_/g, ' ')} (×${selectedPreview.resolved_effects[0].scaled_value})`
            : 'No active effects at this tier'}
        </p>
      )}

      {/* Cost line — only when paid tier selected and preview loaded */}
      {hasPaidTier && selectedPreview !== null && (
        <div className="flex items-center gap-2">
          <p className="text-xs text-amber-400">
            {`−${selectedPreview.resonance_cost} resonance · −${selectedPreview.anima_cost} anima`}
          </p>
          <button
            type="button"
            onClick={() => onOpenDetails(thread)}
            className="text-xs text-primary/80 transition-colors hover:text-primary"
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
      className="space-y-2 rounded-md border border-dashed border-border/50 bg-card/40 p-3 opacity-60"
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
  balanceByResonanceId = {},
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
    // Intentionally omitting selectedPulls, onPullsChange, onAutoRevertNotice,
    // applicableSet, and threadById from deps. This effect must only fire when
    // applicableData itself changes (new context query result). Including
    // selectedPulls would re-run the revert check on every tier click, causing
    // infinite revert loops; including threadById would re-run on every thread
    // list fetch. The stale closures are harmless — selectedPulls is read once
    // at revert time and the names in revertedNames are only for the notice message.
    // eslint-disable-next-line react-hooks/exhaustive-deps -- selectedPulls/onPullsChange/threadById intentionally omitted; see comment above
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
          <span className="text-xs font-normal text-muted-foreground">
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
        <label className="flex cursor-pointer select-none items-center gap-1.5">
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
        <p className="text-xs italic text-muted-foreground" data-testid="no-applicable-threads">
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
              balanceByResonanceId={balanceByResonanceId}
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
        <PullDetailModal
          thread={detailThread}
          open={true}
          onOpenChange={(open) => {
            if (!open) handleCloseDetails();
          }}
        />
      )}
    </div>
  );
}
