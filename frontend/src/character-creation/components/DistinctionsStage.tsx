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
  useAddDistinction,
  useDistinctionCategories,
  useDistinctions,
  useDraftDistinctions,
  useRemoveDistinction,
} from '@/hooks/useDistinctions';
import type { Distinction, DraftDistinctionEntry } from '@/types/distinctions';
import { motion } from 'framer-motion';
import { Check, Loader2, Lock, Search, X } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
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

  // Fetch data
  const { data: categories, isLoading: categoriesLoading } = useDistinctionCategories();
  const { data: draftDistinctions, isLoading: draftDistinctionsLoading } = useDraftDistinctions(
    draft.id
  );

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

  const addDistinction = useAddDistinction(draft.id);
  const removeDistinction = useRemoveDistinction(draft.id);

  // No need for initial category effect since we default to ALL_CATEGORY_SLUG

  // Calculate total cost of selected distinctions
  const totalCost = useMemo(() => {
    if (!draftDistinctions) return 0;
    return draftDistinctions.reduce((sum, entry) => sum + entry.cost, 0);
  }, [draftDistinctions]);

  // Auto-update completion status when distinctions change
  // Traits are complete when user has made any selection (even if points remain)
  // This allows players to continue without selecting all distinctions
  const hasSelections = (draftDistinctions?.length ?? 0) > 0;
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

  const handleAddDistinction = (distinction: Distinction) => {
    if (distinction.is_locked) return;
    addDistinction.mutate({ distinction_id: distinction.id });
  };

  const handleRemoveDistinction = (distinctionId: number) => {
    removeDistinction.mutate(distinctionId);
  };

  // CG Points calculation
  const startingPoints = 100; // Default budget
  const spentPoints = draft.cg_points_spent ?? 0;
  const remainingPoints = draft.cg_points_remaining ?? startingPoints;

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
                      isSelected={draftDistinctions?.some(
                        (d) => d.distinction_id === distinction.id
                      )}
                      onAdd={() => handleAddDistinction(distinction)}
                      onRemove={() => handleRemoveDistinction(distinction.id)}
                      isMutating={addDistinction.isPending || removeDistinction.isPending}
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
                {draftDistinctions?.length ?? 0} selected ({totalCost} points)
              </Badge>
            </CardTitle>
          </CardHeader>
          <CardContent>
            {draftDistinctionsLoading ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
              </div>
            ) : draftDistinctions && draftDistinctions.length > 0 ? (
              <div className="space-y-2">
                {draftDistinctions.map((entry) => (
                  <SelectedDistinctionItem
                    key={entry.distinction_id}
                    entry={entry}
                    onRemove={() => handleRemoveDistinction(entry.distinction_id)}
                    isRemoving={removeDistinction.isPending}
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
  onAdd: () => void;
  onRemove: () => void;
  isMutating?: boolean;
}

function DistinctionCard({
  distinction,
  isSelected,
  onAdd,
  onRemove,
  isMutating,
}: DistinctionCardProps) {
  const isLocked = distinction.is_locked;
  const hasOverflowEffects = distinction.effects_summary.length > 2;
  // Show hover if description is long (truncated by line-clamp-2) or has overflow effects
  const hasLongDescription = distinction.description.length > 120;
  const showHover = !isSelected && (hasOverflowEffects || hasLongDescription);
  const isDisabled = isLocked || isMutating;

  const cardContent = (
    <Card
      className={`cursor-pointer transition-all ${
        isSelected
          ? 'bg-primary/10 ring-2 ring-primary'
          : isDisabled
            ? 'cursor-not-allowed opacity-50'
            : 'hover:ring-1 hover:ring-primary/50'
      }`}
      onClick={() => {
        if (isDisabled) return;
        if (isSelected) {
          onRemove();
        } else {
          onAdd();
        }
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
  entry: DraftDistinctionEntry;
  onRemove: () => void;
  isRemoving: boolean;
}

function SelectedDistinctionItem({ entry, onRemove, isRemoving }: SelectedDistinctionItemProps) {
  return (
    <div className="flex items-center justify-between rounded-md border p-2">
      <div className="flex items-center gap-2">
        <span className="text-sm font-medium">{entry.distinction_name}</span>
        <Badge variant="outline" className="text-xs">
          {entry.cost > 0 ? '+' : ''}
          {entry.cost}
        </Badge>
        {entry.rank > 1 && (
          <Badge variant="secondary" className="text-xs">
            Rank {entry.rank}
          </Badge>
        )}
      </div>
      <Button
        variant="ghost"
        size="sm"
        className="h-7 w-7 p-0 text-muted-foreground hover:text-destructive"
        onClick={onRemove}
        disabled={isRemoving}
      >
        {isRemoving ? <Loader2 className="h-4 w-4 animate-spin" /> : <X className="h-4 w-4" />}
      </Button>
    </div>
  );
}
