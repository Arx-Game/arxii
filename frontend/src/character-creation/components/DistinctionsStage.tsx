/**
 * Stage 6: Distinctions Selection
 *
 * Players select advantages and disadvantages (distinctions) that shape
 * their character. Categories are displayed as tabs, with search filtering
 * and lock status indicators.
 */

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { HoverCard, HoverCardContent, HoverCardTrigger } from '@/components/ui/hover-card';
import { Input } from '@/components/ui/input';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import {
  useBatchSyncDistinctions,
  useDistinctionCategories,
  useDistinctions,
  useDraftDistinctions,
} from '@/hooks/useDistinctions';
import type { Distinction } from '@/types/distinctions';
import { motion } from 'framer-motion';
import { Check, Loader2, Lock, Search, X } from 'lucide-react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useUpdateDraft } from '../queries';
import type { CharacterDraft } from '../types';
import { CGPointsWidget } from './CGPointsWidget';

interface DistinctionsStageProps {
  draft: CharacterDraft;
}

const ALL_CATEGORY_SLUG = '__all__';

export function DistinctionsStage({ draft }: DistinctionsStageProps) {
  const updateDraft = useUpdateDraft();
  const [selectedCategory, setSelectedCategory] = useState<string>(ALL_CATEGORY_SLUG);
  const [searchQuery, setSearchQuery] = useState('');

  // Local state for selections - store full objects to display across category switches
  const [localSelections, setLocalSelections] = useState<Map<number, Distinction>>(new Map());
  const [isInitialized, setIsInitialized] = useState(false);

  // Fetch data
  const { data: categories, isLoading: categoriesLoading } = useDistinctionCategories();
  const { data: draftDistinctions } = useDraftDistinctions(draft.id);

  // Fetch all distinctions (no filter) for initializing selections
  const { data: allDistinctions } = useDistinctions({}, { enabled: !isInitialized });

  // Track original server state for diffing on sync
  const serverSelectionsRef = useRef<Set<number>>(new Set());

  // Batch sync hook for committing changes
  const batchSync = useBatchSyncDistinctions(draft.id);

  // Initialize local selections from server data (once)
  useEffect(() => {
    if (draftDistinctions && allDistinctions && !isInitialized) {
      const serverIds = new Set(draftDistinctions.map((d) => d.distinction_id));
      const initialSelections = new Map<number, Distinction>();
      for (const d of allDistinctions) {
        if (serverIds.has(d.id)) {
          initialSelections.set(d.id, d);
        }
      }
      setLocalSelections(initialSelections);
      serverSelectionsRef.current = serverIds;
      setIsInitialized(true);
    }
  }, [draftDistinctions, allDistinctions, isInitialized]);

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
    for (const d of localSelections.values()) {
      sum += d.cost_per_rank;
    }
    return sum;
  }, [localSelections]);

  // Sync on component unmount (when leaving the stage)
  useEffect(() => {
    return () => {
      const currentIds = new Set(localSelections.keys());
      const serverIds = serverSelectionsRef.current;

      const toAdd = [...currentIds].filter((id) => !serverIds.has(id));
      const toRemove = [...serverIds].filter((id) => !currentIds.has(id));

      if (toAdd.length > 0 || toRemove.length > 0) {
        // Fire and forget - we can't await in cleanup
        batchSync.mutate({ toAdd, toRemove });
      }
    };
  }, [localSelections, batchSync]);

  // Auto-update completion status based on local selections
  const hasSelections = localSelections.size > 0;
  useEffect(() => {
    const currentComplete = draft.draft_data.traits_complete;
    if (currentComplete !== hasSelections) {
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
  }, [hasSelections, draft.id, draft.draft_data, updateDraft]);

  const handleToggleDistinction = (distinction: Distinction) => {
    if (distinction.is_locked) return;

    setLocalSelections((prev) => {
      const next = new Map(prev);
      if (next.has(distinction.id)) {
        next.delete(distinction.id);
      } else {
        next.set(distinction.id, distinction);
      }
      return next;
    });
  };

  // CG Points calculation - use local cost calculation
  const startingPoints = 100; // Default budget
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
          <h2 className="text-2xl font-bold">Distinctions</h2>
          <p className="mt-2 text-muted-foreground">
            Select advantages and disadvantages that define your character's unique traits and
            abilities.
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
                  {distinctions.map((distinction) => (
                    <DistinctionCard
                      key={distinction.id}
                      distinction={distinction}
                      isSelected={localSelections.has(distinction.id)}
                      onToggle={() => handleToggleDistinction(distinction)}
                    />
                  ))}
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
                {[...localSelections.values()].map((distinction) => (
                  <SelectedDistinctionItem
                    key={distinction.id}
                    distinction={distinction}
                    onRemove={() => handleToggleDistinction(distinction)}
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

      {/* Sidebar: CG Points Widget */}
      <div className="hidden lg:block">
        <CGPointsWidget starting={startingPoints} spent={spentPoints} remaining={remainingPoints} />
      </div>
    </div>
  );
}

// =============================================================================
// Sub-components
// =============================================================================

interface DistinctionCardProps {
  distinction: Distinction;
  isSelected?: boolean;
  onToggle: () => void;
}

function DistinctionCard({ distinction, isSelected, onToggle }: DistinctionCardProps) {
  const isLocked = distinction.is_locked;
  const hasOverflowEffects = distinction.effects_summary.length > 2;
  // Show hover if description is long (truncated by line-clamp-2) or has overflow effects
  // Use 80 chars threshold since line-clamp-2 with small text truncates around there
  const hasLongDescription = distinction.description.length > 80;
  const showHover = !isSelected && (hasOverflowEffects || hasLongDescription);

  const cardContent = (
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
    >
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between gap-2">
          <CardTitle className="text-sm font-medium">{distinction.name}</CardTitle>
          <div className="flex items-center gap-1">
            {isSelected && <Check className="h-4 w-4 text-primary" />}
            {isLocked && <Lock className="h-3 w-3 text-muted-foreground" />}
            <Badge variant="outline" className="text-xs">
              {distinction.cost_per_rank > 0 ? '+' : ''}
              {distinction.cost_per_rank}
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
              <Badge key={idx} variant="secondary" className="text-xs">
                {effect}
              </Badge>
            ))}
            {!isSelected && distinction.effects_summary.length > 2 && (
              <Badge variant="secondary" className="text-xs">
                +{distinction.effects_summary.length - 2} more effects
              </Badge>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );

  // Only show hover tooltip for unselected cards with overflow effects
  if (!showHover) {
    return cardContent;
  }

  return (
    <HoverCard openDelay={200} closeDelay={100}>
      <HoverCardTrigger asChild>{cardContent}</HoverCardTrigger>
      <HoverCardContent className="w-80">
        <div className="space-y-2">
          <h4 className="text-sm font-semibold">{distinction.name}</h4>
          <p className="text-xs text-muted-foreground">{distinction.description}</p>
          <div className="space-y-1">
            <p className="text-xs font-medium">Effects:</p>
            <div className="flex flex-wrap gap-1">
              {distinction.effects_summary.map((effect, idx) => (
                <Badge key={idx} variant="secondary" className="text-xs">
                  {effect}
                </Badge>
              ))}
            </div>
          </div>
        </div>
      </HoverCardContent>
    </HoverCard>
  );
}

interface SelectedDistinctionItemProps {
  distinction: Distinction;
  onRemove: () => void;
}

function SelectedDistinctionItem({ distinction, onRemove }: SelectedDistinctionItemProps) {
  return (
    <div className="flex items-center justify-between rounded-md border p-2">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">{distinction.name}</span>
        <Badge variant="outline" className="text-xs">
          {distinction.cost_per_rank > 0 ? '+' : ''}
          {distinction.cost_per_rank}
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
