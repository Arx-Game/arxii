/**
 * Stage 4: Distinctions (#3630).
 *
 * Advantages and disadvantages as an instrument: a category choice row, then
 * the category's distinctions as stat rows with the purse at the head.
 * Pressing a distinction's name writes what it does into the margin
 * (replacing the hover detail panel, Decision 6). Selections are stored
 * locally and auto-saved when navigating away.
 */

import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import {
  useDistinctionCategories,
  useDistinctions,
  useDraftDistinctions,
  useSyncDistinctions,
} from '@/hooks/useDistinctions';
import type { Distinction } from '@/types/distinctions';
import {
  ChapterLeaf,
  ChoiceRow,
  CodexLine,
  ConfirmDialog,
  InstrumentFrame,
  InstrumentGroup,
  Marginalia,
  Note,
  RecordRail,
  StatRow,
} from '../folio';
import { useCGExplanations, useCGPointBudget, useUpdateDraft } from '../queries';
import type { CharacterDraft } from '../types';
import { Stage } from '../types';

interface DistinctionsStageProps {
  draft: CharacterDraft;
  onRegisterBeforeLeave?: (check: () => Promise<boolean>) => (() => void) | void;
}

/**
 * The category row's first option: no category filter at all, so search
 * reaches the whole catalog instead of one category's slice.
 */
const ALL_CATEGORIES = 'all';

/** Format a cost value with a +/- prefix for display. */
function formatCost(cost: number): string {
  return `${cost > 0 ? '+' : ''}${cost}`;
}

/**
 * A row's sub-line: its cost, plus why it is locked when it is. The reason is
 * the useful half, so it is visible here rather than only in the raise
 * button's title; "locked" is the fallback for a lock with no stated reason.
 */
function subFor(distinction: Distinction): string {
  const cost = `${formatCost(distinction.cost_per_rank)} per rank`;
  if (!distinction.is_locked) return cost;
  return `${cost} · ${distinction.lock_reason || 'locked'}`;
}

/** Why the raise button is disabled, if it is; `undefined` when it isn't. */
function increaseTitleFor(distinction: Distinction, rank: number): string | undefined {
  if (distinction.is_locked) return distinction.lock_reason ?? 'Locked';
  if (rank >= distinction.max_rank) return `At ${distinction.max_rank}, the most it can be`;
  return undefined;
}

export function DistinctionsStage({ draft, onRegisterBeforeLeave }: DistinctionsStageProps) {
  const updateDraft = useUpdateDraft();
  const { data: copy } = useCGExplanations();
  const { data: cgBudget } = useCGPointBudget();
  const syncDistinctions = useSyncDistinctions(draft.id);

  const [category, setCategory] = useState<string>(ALL_CATEGORIES);
  const [search, setSearch] = useState('');
  const [why, setWhy] = useState<Distinction | null>(null);
  const [announce, setAnnounce] = useState('');
  const [confirmReset, setConfirmReset] = useState(false);

  // Local state for selections - store full objects with rank to display across category switches
  const [localSelections, setLocalSelections] = useState<
    Map<number, { distinction: Distinction; rank: number }>
  >(new Map());
  const [isInitialized, setIsInitialized] = useState(false);

  // Track server state to detect changes (ranks map doubles as ID set via .has())
  const serverRanksRef = useRef<Map<number, number>>(new Map());

  // Fetch data
  const { data: categories, isLoading: categoriesLoading } = useDistinctionCategories();
  const { data: draftDistinctions } = useDraftDistinctions(draft.id);

  // Fetch all distinctions (no filter) for initializing selections
  const { data: allDistinctions } = useDistinctions({}, { enabled: !isInitialized });

  // Initialize local selections from server data (once)
  useEffect(() => {
    if (!draftDistinctions || !allDistinctions || isInitialized) return;

    const serverEntries = new Map(draftDistinctions.map((d) => [d.distinction_id, d.rank]));
    const newSelections = new Map<number, { distinction: Distinction; rank: number }>();
    for (const d of allDistinctions) {
      const rank = serverEntries.get(d.id);
      if (rank !== undefined) {
        newSelections.set(d.id, { distinction: d, rank });
      }
    }
    setLocalSelections(newSelections);
    serverRanksRef.current = new Map(draftDistinctions.map((d) => [d.distinction_id, d.rank]));
    setIsInitialized(true);
  }, [draftDistinctions, allDistinctions, isInitialized]);

  // Check if there are unsaved changes
  const hasChanges = useCallback(() => {
    if (!isInitialized) return false;
    const serverRanks = serverRanksRef.current;
    if (localSelections.size !== serverRanks.size) return true;
    for (const [id, entry] of localSelections) {
      if (entry.rank !== serverRanks.get(id)) return true;
    }
    return false;
  }, [localSelections, isInitialized]);

  // Auto-save when leaving the stage
  useEffect(() => {
    if (!onRegisterBeforeLeave) return;

    const saveBeforeLeave = async (): Promise<boolean> => {
      if (!hasChanges()) return true;

      try {
        const entries = [...localSelections.entries()].map(([id, entry]) => ({
          id,
          rank: entry.rank,
        }));
        const result = await syncDistinctions.mutateAsync(entries);
        serverRanksRef.current = new Map(
          [...localSelections.entries()].map(([id, entry]) => [id, entry.rank])
        );

        if (result?.stat_adjustments?.length > 0) {
          for (const adj of result.stat_adjustments) {
            const statName = adj.stat.charAt(0).toUpperCase() + adj.stat.slice(1);
            toast.info(
              `${statName} reduced from ${adj.old_display} to ${adj.new_display}. ${adj.reason}. You have points to redistribute in Attributes.`,
              { duration: 6000 }
            );
          }
        }

        return true;
      } catch (error) {
        console.error('[Distinctions] Auto-save failed:', error);
        const discard = window.confirm(
          'Failed to save distinctions. Discard changes and continue anyway?'
        );
        return discard;
      }
    };

    // Return the unregister as cleanup (2026-07 audit): without it, this
    // stage's save closure stayed registered after unmount and re-fired on
    // every later navigation, syncing stale selections over newer edits.
    return onRegisterBeforeLeave(saveBeforeLeave) ?? undefined;
  }, [onRegisterBeforeLeave, hasChanges, localSelections, syncDistinctions]);

  // The category row opens on "All", so a search covers the whole catalog
  // until the player narrows it.
  const showingAll = category === ALL_CATEGORIES;

  const { data: distinctions, isLoading: distinctionsLoading } = useDistinctions({
    category: showingAll ? undefined : category,
    search: search || undefined,
    draftId: draft.id,
  });

  // Calculate total cost from local selections
  const totalCost = useMemo(() => {
    let sum = 0;
    for (const entry of localSelections.values()) {
      sum += entry.distinction.cost_per_rank * entry.rank;
    }
    return sum;
  }, [localSelections]);

  // Auto-update completion status based on local selections
  const hasSelections = localSelections.size > 0;
  const lastSentTraitsComplete = useRef<boolean | null>(null);

  useEffect(() => {
    if (!isInitialized) return;
    if (lastSentTraitsComplete.current !== hasSelections) {
      lastSentTraitsComplete.current = hasSelections;
      updateDraft.mutate({
        draftId: draft.id,
        data: {
          draft_data: {
            traits_complete: hasSelections,
          },
        },
      });
    }
    // Intentionally exclude updateDraft from deps to prevent infinite loops
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasSelections, draft.id, isInitialized]);

  const rankOf = (id: number) => localSelections.get(id)?.rank ?? 0;

  const setRank = (distinction: Distinction, rawValue: number) => {
    const value = Math.max(0, Math.min(distinction.max_rank, rawValue));
    setLocalSelections((prev) => {
      const next = new Map(prev);
      if (value <= 0) {
        next.delete(distinction.id);
      } else {
        next.set(distinction.id, { distinction, rank: value });
      }
      return next;
    });
    setAnnounce(`${distinction.name} ${value}.`);
  };

  const handleReset = () => {
    setLocalSelections(new Map());
    setConfirmReset(false);
  };

  // CG Points calculation
  const starting = cgBudget?.starting_points ?? 100;
  const spent = totalCost;
  const chosenCount = localSelections.size;
  const chosenList = [...localSelections.values()];

  if (categoriesLoading) {
    return (
      <p className="ledger-line" aria-busy="true">
        Loading distinctions…
      </p>
    );
  }

  const list = distinctions ?? [];
  const sortedCategories = [...(categories ?? [])].sort(
    (a, b) => a.display_order - b.display_order
  );
  // One group per category under "All", one group under a named category.
  // Empty groups are dropped rather than shown as furniture.
  const groups = (
    showingAll ? sortedCategories : sortedCategories.filter((c) => c.slug === category)
  )
    .map((c) => ({ category: c, rows: list.filter((d) => d.category_slug === c.slug) }))
    .filter((group) => group.rows.length > 0);

  /**
   * What sits inside the instrument frame: one ledger line, or the groups.
   * Written as a function rather than nested ternaries so each case reads on
   * its own line.
   */
  const frameBody = () => {
    if (sortedCategories.length === 0) return <p className="ledger-line">No categories yet.</p>;
    if (distinctionsLoading) {
      return (
        <p className="ledger-line" aria-busy="true">
          Loading distinctions…
        </p>
      );
    }
    if (groups.length === 0) return <p className="ledger-line">No distinctions match.</p>;
    return groups.map((group) => (
      <InstrumentGroup
        key={group.category.slug}
        title={group.category.name}
        gloss={group.category.description || undefined}
      >
        {group.rows.map((d) => (
          <StatRow
            key={d.id}
            id={`lbl-dist-${d.id}`}
            name={d.name}
            sub={subFor(d)}
            value={rankOf(d.id)}
            max={d.max_rank}
            onChange={(v) => setRank(d, v)}
            canDecrease={rankOf(d.id) > 0}
            canIncrease={!d.is_locked && rankOf(d.id) < d.max_rank}
            increaseTitle={increaseTitleFor(d, rankOf(d.id))}
            onWhy={() => setWhy(d)}
            whyOpen={why?.id === d.id}
          />
        ))}
      </InstrumentGroup>
    ));
  };

  const rail = (
    <>
      <RecordRail
        rows={[
          { label: 'Origin', value: draft.selected_area?.name },
          { label: 'Beginnings', value: draft.selected_beginnings?.name },
          { label: 'Species', value: draft.selected_species?.name },
          { label: 'Distinctions', value: `${chosenCount} chosen, ${spent} points` },
        ]}
        ledger="Stage 4 of 11"
      />
      <Marginalia id="note-dist">
        <span className="note" id="why-note" role="status">
          {why ? (
            <>
              <b>{why.name}.</b> {why.description}
              {why.effects_summary.map((effect, i) => (
                <Fragment key={i}>
                  <br />
                  {effect.text}
                </Fragment>
              ))}
              <br />
              Up to rank {why.max_rank}.
              <CodexLine entryId={why.codex_entry_ids?.[0]} name={why.name} />
            </>
          ) : (
            // PLACEHOLDER: Apostate rewrite
            <>
              <b>Distinctions.</b> Select a distinction’s name to read what it does.
            </>
          )}
        </span>
        {chosenList.length > 0 && (
          <Note lead="Selected">
            {chosenList.map((entry, i) => (
              <Fragment key={entry.distinction.id}>
                {i > 0 && <br />}
                {entry.distinction.name} · rank {entry.rank}
              </Fragment>
            ))}
          </Note>
        )}
      </Marginalia>
    </>
  );

  return (
    <ChapterLeaf
      stage={Stage.DISTINCTIONS}
      title={copy?.distinctions_heading ?? 'Your Distinctions'}
      intro={copy?.distinctions_intro}
      aside={rail}
    >
      <span className="vh" role="status">
        {announce}
      </span>
      <h2 className="section-h" id="dist-cat">
        Category
      </h2>
      <ChoiceRow
        label="Category"
        options={[
          { value: ALL_CATEGORIES, label: 'All' },
          ...sortedCategories.map((c) => ({ value: c.slug, label: c.name })),
        ]}
        value={category}
        onChange={(slug) => slug && setCategory(slug)}
      />
      <div className="instr-search">
        <label htmlFor="dist-search" className="vh">
          Search distinctions
        </label>
        <input
          id="dist-search"
          type="search"
          placeholder="Search by name, description, or effects"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        {search && (
          <button type="button" className="btn-quiet" onClick={() => setSearch('')}>
            Clear search
          </button>
        )}
      </div>
      <InstrumentFrame
        label="Distinctions"
        ledger={{
          left: `${chosenCount} chosen`,
          right: (
            <>
              Points remaining: <b>{starting - spent}</b> of <b>{starting}</b>
              {starting - spent < 0 && <>, over by {spent - starting}</>}
            </>
          ),
          over: starting - spent < 0,
        }}
      >
        {frameBody()}
      </InstrumentFrame>
      <p className="ledger-line">
        <button
          type="button"
          className="btn-quiet"
          onClick={() => setConfirmReset(true)}
          disabled={chosenCount === 0}
        >
          Clear all distinctions
        </button>
      </p>
      <ConfirmDialog
        open={confirmReset}
        title="Clear all distinctions"
        confirmLabel="Clear all"
        cancelLabel="Keep them"
        onConfirm={handleReset}
        onCancel={() => setConfirmReset(false)}
      >
        This removes every distinction you have chosen on this stage.
      </ConfirmDialog>
    </ChapterLeaf>
  );
}
