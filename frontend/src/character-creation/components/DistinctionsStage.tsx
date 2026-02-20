/**
 * Stage 4: Distinctions Selection
 *
 * Players select advantages and disadvantages (distinctions) that shape
 * their character. Categories are displayed as tabs, with search filtering
 * and lock status indicators.
 *
 * Selections are stored locally and auto-saved when navigating away.
 */

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { CodexTerm } from '@/codex/components/CodexTerm';
import {
  useDistinctionCategories,
  useDistinctions,
  useDraftDistinctions,
  useSyncDistinctions,
} from '@/hooks/useDistinctions';
import type { Distinction, EffectSummary } from '@/types/distinctions';
import { AnimatePresence, motion } from 'framer-motion';
import { Check, Loader2, Lock, RotateCcw, Search, X } from 'lucide-react';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { toast } from 'sonner';
import { useUpdateDraft } from '../queries';
import type { CharacterDraft } from '../types';
import { CGPointsWidget } from './CGPointsWidget';

interface DistinctionsStageProps {
  draft: CharacterDraft;
  onRegisterBeforeLeave?: (check: () => Promise<boolean>) => void;
}

const ALL_CATEGORY_SLUG = '__all__';

/** Format a cost value with a +/- prefix for display. */
function formatCost(cost: number): string {
  return `${cost > 0 ? '+' : ''}${cost}`;
}

export function DistinctionsStage({ draft, onRegisterBeforeLeave }: DistinctionsStageProps) {
  const updateDraft = useUpdateDraft();
  const syncDistinctions = useSyncDistinctions(draft.id);

  const [selectedCategory, setSelectedCategory] = useState<string>(ALL_CATEGORY_SLUG);
  const [searchQuery, setSearchQuery] = useState('');
  const [hoveredDistinction, setHoveredDistinction] = useState<Distinction | null>(null);
  const [activeDistinction, setActiveDistinction] = useState<Distinction | null>(null);

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

    onRegisterBeforeLeave(saveBeforeLeave);
  }, [onRegisterBeforeLeave, hasChanges, localSelections, syncDistinctions]);

  // Build categories list with "All" option prepended
  const categoriesWithAll = useMemo(() => {
    if (!categories) return [];
    return [{ slug: ALL_CATEGORY_SLUG, name: 'All' }, ...categories];
  }, [categories]);

  // When "All" is selected, don't pass category filter
  const categoryFilter = selectedCategory === ALL_CATEGORY_SLUG ? undefined : selectedCategory;

  const { data: distinctions, isLoading: distinctionsLoading } = useDistinctions(
    {
      category: categoryFilter,
      search: searchQuery || undefined,
      draftId: draft.id,
    },
    { enabled: !!selectedCategory }
  );

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
    if (lastSentTraitsComplete.current !== hasSelections) {
      lastSentTraitsComplete.current = hasSelections;
      updateDraft.mutate({
        draftId: draft.id,
        data: {
          draft_data: {
            ...draft.draft_data,
            traits_complete: hasSelections,
          },
        },
      });
    }
    // Intentionally exclude updateDraft from deps to prevent infinite loops
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [hasSelections, draft.id]);

  const handleToggleDistinction = (distinction: Distinction) => {
    if (distinction.is_locked) return;
    setActiveDistinction(distinction);

    setLocalSelections((prev) => {
      const next = new Map(prev);
      const existing = next.get(distinction.id);

      if (!existing) {
        // Not selected -> select at rank 1
        next.set(distinction.id, { distinction, rank: 1 });
      } else if (existing.rank < distinction.max_rank) {
        // Increment rank
        next.set(distinction.id, { distinction, rank: existing.rank + 1 });
      } else {
        // At max rank -> deselect
        next.delete(distinction.id);
      }
      return next;
    });
  };

  const handleRemoveDistinction = (distinctionId: number) => {
    setLocalSelections((prev) => {
      const next = new Map(prev);
      next.delete(distinctionId);
      return next;
    });
  };

  const handleReset = () => {
    setLocalSelections(new Map());
  };

  // CG Points calculation
  const startingPoints = 100;
  const spentPoints = totalCost;
  const remainingPoints = startingPoints - totalCost;

  if (categoriesLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  return (
    <div className="grid gap-8 lg:grid-cols-[1fr_300px]">
      {/* Main Content */}
      <motion.div
        initial={{ opacity: 0, y: 20 }}
        animate={{ opacity: 1, y: 0 }}
        exit={{ opacity: 0, y: -20 }}
        transition={{ duration: 0.3 }}
        className="space-y-6"
      >
        <div>
          <div className="flex items-center justify-between">
            <h2 className="theme-heading text-2xl font-bold">Distinctions</h2>
            {localSelections.size > 0 && (
              <Button variant="outline" size="sm" onClick={handleReset}>
                <RotateCcw className="mr-1 h-3 w-3" />
                Reset
              </Button>
            )}
          </div>
          <p className="mt-2 text-muted-foreground">
            Select advantages and disadvantages that define your character's unique traits and
            abilities. Changes are saved automatically when you navigate away.
          </p>
        </div>

        {/* Category Tabs */}
        <Tabs value={selectedCategory} onValueChange={setSelectedCategory}>
          <div className="overflow-x-auto">
            <TabsList className="inline-flex w-auto min-w-full justify-start">
              {categoriesWithAll.map((category) => (
                <TabsTrigger
                  key={category.slug}
                  value={category.slug}
                  className="whitespace-nowrap"
                >
                  {category.name}
                </TabsTrigger>
              ))}
            </TabsList>
          </div>

          {/* Search Input */}
          <div className="relative mt-4">
            <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
            <Input
              placeholder="Search by name, description, or effects..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="pl-9"
            />
            {searchQuery && (
              <Button
                variant="ghost"
                size="sm"
                className="absolute right-1 top-1/2 h-7 w-7 -translate-y-1/2 p-0"
                onClick={() => setSearchQuery('')}
              >
                <X className="h-4 w-4" />
              </Button>
            )}
          </div>

          {/* Distinction List */}
          {categoriesWithAll.map((category) => (
            <TabsContent key={category.slug} value={category.slug} className="mt-4 space-y-3">
              {distinctionsLoading ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
                </div>
              ) : distinctions && distinctions.length > 0 ? (
                <div className="grid gap-3 sm:grid-cols-2">
                  {distinctions.map((distinction) => {
                    const entry = localSelections.get(distinction.id);
                    return (
                      <DistinctionCard
                        key={distinction.id}
                        distinction={distinction}
                        isSelected={!!entry}
                        selectedRank={entry?.rank}
                        onToggle={() => handleToggleDistinction(distinction)}
                        onHover={setHoveredDistinction}
                      />
                    );
                  })}
                </div>
              ) : (
                <Card>
                  <CardContent className="py-8">
                    <p className="text-center text-sm text-muted-foreground">
                      {searchQuery
                        ? 'No distinctions match your search.'
                        : 'No distinctions available in this category.'}
                    </p>
                  </CardContent>
                </Card>
              )}
            </TabsContent>
          ))}
        </Tabs>

        {/* Mobile: Distinction detail below grid */}
        {activeDistinction && (
          <div className="lg:hidden">
            <DistinctionDetailPanel distinction={activeDistinction} />
          </div>
        )}

        {/* Selected Distinctions Panel */}
        <Card>
          <CardHeader className="pb-3">
            <CardTitle className="flex items-center justify-between text-base">
              <span>Selected Distinctions</span>
              <Badge variant="secondary">
                {localSelections.size} selected ({totalCost} points)
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {!isInitialized ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : localSelections.size > 0 ? (
              <div className="space-y-2">
                {[...localSelections.values()].map((entry) => (
                  <SelectedDistinctionItem
                    key={entry.distinction.id}
                    distinction={entry.distinction}
                    rank={entry.rank}
                    onRemove={() => handleRemoveDistinction(entry.distinction.id)}
                  />
                ))}
              </div>
            ) : (
              <p className="py-4 text-center text-sm text-muted-foreground">
                No distinctions selected yet. Browse the categories above to add some.
              </p>
            )}
          </CardContent>
        </Card>
      </motion.div>

      {/* Sidebar: CG Points Widget + Hover Detail */}
      <div className="hidden lg:block">
        <div className="sticky top-4 space-y-4">
          <CGPointsWidget
            starting={startingPoints}
            spent={spentPoints}
            remaining={remainingPoints}
          />
          <DistinctionDetailPanel distinction={hoveredDistinction} />
        </div>
      </div>
    </div>
  );
}

// =============================================================================
// Sub-components
// =============================================================================

/** Detail panel showing full distinction info on hover (desktop) or tap (mobile) */
function DistinctionDetailPanel({ distinction }: { distinction: Distinction | null }) {
  if (!distinction) {
    return (
      <Card className="bg-muted/30">
        <CardContent className="py-8 text-center text-sm text-muted-foreground">
          Hover over a distinction to see its full description and effects.
        </CardContent>
      </Card>
    );
  }

  return (
    <AnimatePresence mode="wait">
      <motion.div
        key={distinction.id}
        initial={{ opacity: 0, x: 10 }}
        animate={{ opacity: 1, x: 0 }}
        exit={{ opacity: 0, x: -10 }}
        transition={{ duration: 0.25 }}
      >
        <Card>
          <CardHeader className="pb-2">
            <div className="flex items-center justify-between">
              <CardTitle className="text-sm font-medium">{distinction.name}</CardTitle>
              <Badge variant="outline" className="text-xs">
                {formatCost(distinction.cost_per_rank)}
              </Badge>
            </div>
          </CardHeader>
          <CardContent className="space-y-3 pt-0">
            <p className="text-xs text-muted-foreground">{distinction.description}</p>
            {distinction.effects_summary.length > 0 && (
              <div className="space-y-1">
                <p className="text-xs font-medium">Effects:</p>
                <div className="flex flex-wrap gap-1">
                  {distinction.effects_summary.map((effect, idx) => (
                    <EffectBadge key={idx} effect={effect} />
                  ))}
                </div>
              </div>
            )}
            {distinction.max_rank > 1 && (
              <p className="text-xs text-muted-foreground">Max rank: {distinction.max_rank}</p>
            )}
          </CardContent>
        </Card>
      </motion.div>
    </AnimatePresence>
  );
}

interface DistinctionCardProps {
  distinction: Distinction;
  isSelected?: boolean;
  selectedRank?: number;
  onToggle: () => void;
  onHover: (distinction: Distinction | null) => void;
}

function DistinctionCard({
  distinction,
  isSelected,
  selectedRank,
  onToggle,
  onHover,
}: DistinctionCardProps) {
  const isLocked = distinction.is_locked;

  return (
    <Card
      className={`cursor-pointer transition-all ${
        isSelected
          ? 'bg-primary/10 ring-2 ring-primary'
          : isLocked
            ? 'cursor-not-allowed opacity-50'
            : 'hover:ring-1 hover:ring-primary/50'
      }`}
      onClick={() => {
        if (isLocked) return;
        onToggle();
      }}
      onMouseEnter={() => onHover(distinction)}
      onMouseLeave={() => onHover(null)}
    >
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-sm font-medium">{distinction.name}</CardTitle>
          <div className="flex items-center gap-1">
            {isSelected && <Check className="h-4 w-4 text-primary" />}
            {isLocked && <Lock className="h-3 w-3 text-muted-foreground" />}
            <Badge variant="outline" className="text-xs">
              {formatCost(distinction.cost_per_rank * (selectedRank || 1))}
            </Badge>
          </div>
        </div>
      </CardHeader>
      <CardContent className="space-y-2 pt-0">
        <CardDescription className="line-clamp-2 text-xs">
          {distinction.description}
        </CardDescription>
        {isLocked && distinction.lock_reason && (
          <p className="text-xs italic text-destructive">{distinction.lock_reason}</p>
        )}
        {distinction.effects_summary.length > 0 && (
          <div className="flex flex-wrap gap-1">
            {(isSelected
              ? distinction.effects_summary
              : distinction.effects_summary.slice(0, 2)
            ).map((effect, idx) => (
              <EffectBadge key={idx} effect={effect} />
            ))}
            {!isSelected && distinction.effects_summary.length > 2 && (
              <Badge variant="secondary" className="text-xs">
                +{distinction.effects_summary.length - 2} more effects
              </Badge>
            )}
          </div>
        )}
        {distinction.max_rank > 1 && (
          <RankPips maxRank={distinction.max_rank} currentRank={selectedRank ?? 0} />
        )}
      </CardContent>
    </Card>
  );
}

interface SelectedDistinctionItemProps {
  distinction: Distinction;
  rank: number;
  onRemove: () => void;
}

function SelectedDistinctionItem({ distinction, rank, onRemove }: SelectedDistinctionItemProps) {
  const totalCost = distinction.cost_per_rank * rank;

  return (
    <div className="flex items-center justify-between rounded-md border p-2">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">{distinction.name}</span>
        {distinction.max_rank > 1 && <RankPips maxRank={distinction.max_rank} currentRank={rank} />}
        <Badge variant="outline" className="text-xs">
          {formatCost(totalCost)}
        </Badge>
      </div>
      <Button
        variant="ghost"
        size="sm"
        className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
        onClick={onRemove}
      >
        <X className="h-4 w-4" />
      </Button>
    </div>
  );
}

interface EffectBadgeProps {
  effect: EffectSummary;
}

/**
 * Renders an effect badge with optional CodexTerm link.
 * If the effect has a codex_entry_id, the text becomes clickable
 * to open the Codex modal for that term.
 */
function EffectBadge({ effect }: EffectBadgeProps) {
  if (effect.codex_entry_id) {
    return (
      <Badge variant="secondary" className="text-xs">
        <CodexTerm entryId={effect.codex_entry_id}>{effect.text}</CodexTerm>
      </Badge>
    );
  }
  return (
    <Badge variant="secondary" className="text-xs">
      {effect.text}
    </Badge>
  );
}

interface RankPipsProps {
  maxRank: number;
  currentRank: number;
}

/**
 * Visual rank indicator showing filled/empty circles.
 * Only rendered for multi-rank distinctions (maxRank > 1).
 */
function RankPips({ maxRank, currentRank }: RankPipsProps) {
  if (maxRank <= 1) return null;

  return (
    <div className="flex items-center gap-1">
      {Array.from({ length: maxRank }, (_, i) => (
        <div
          key={i}
          className={`h-2 w-2 rounded-full border ${
            i < currentRank
              ? 'border-primary bg-primary'
              : 'border-muted-foreground/50 bg-transparent'
          }`}
        />
      ))}
    </div>
  );
}
