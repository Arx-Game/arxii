/**
 * TechniqueSelector — third step of the GiftStage funnel (#2426 Task 10).
 *
 * Lists the technique options (pool ∪ signature) for the chosen gift, grouped
 * by category using the same Offense/Defense/Enhancement/Affliction/Utility
 * labels the old CantripSelector used for cantrip archetypes. Picks are capped
 * at `draft.starting_technique_picks` (base 1 + distinction bonus).
 */

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { CodexTerm } from '@/codex/components/CodexTerm';
import { cn } from '@/lib/utils';
import { CheckCircle2, Loader2 } from 'lucide-react';
import { useEffect } from 'react';
import { useCGTechniqueOptions, useUpdateDraft } from '../../queries';
import type { CGTechniqueOption, CharacterDraft } from '../../types';

const CATEGORY_LABELS: Record<CGTechniqueOption['category'], string> = {
  attack: 'Offense',
  defense: 'Defense',
  buff: 'Enhancement',
  debuff: 'Affliction',
  utility: 'Utility',
};

const CATEGORY_ORDER: CGTechniqueOption['category'][] = [
  'attack',
  'defense',
  'buff',
  'debuff',
  'utility',
];

interface TechniqueSelectorProps {
  draft: CharacterDraft;
  giftId: number;
}

export function TechniqueSelector({ draft, giftId }: TechniqueSelectorProps) {
  const updateDraft = useUpdateDraft();
  const { data: options, isLoading } = useCGTechniqueOptions(draft.id, giftId);
  const selectedIds = draft.draft_data.selected_technique_ids ?? [];
  const picks = draft.starting_technique_picks;
  const traditionName = draft.selected_tradition?.name ?? 'Tradition';

  // Clear stale picks when the option set changes (gift swap, tradition swap, etc.)
  useEffect(() => {
    if (!options) return;
    const availableIds = new Set(options.map((t) => t.id));
    const filtered = selectedIds.filter((id) => availableIds.has(id));
    if (filtered.length !== selectedIds.length) {
      updateDraft.mutate({
        draftId: draft.id,
        data: {
          draft_data: {
            selected_technique_ids: filtered,
          },
        },
      });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps -- only re-run when the option set changes, not on every draft mutation
  }, [options]);

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-8">
        <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        <span className="ml-2 text-muted-foreground">Loading techniques...</span>
      </div>
    );
  }

  if (!options || options.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">No techniques are available for this gift.</p>
    );
  }

  const atBudget = selectedIds.length >= picks;

  const toggle = (techniqueId: number) => {
    const isSelected = selectedIds.includes(techniqueId);
    const next = isSelected
      ? selectedIds.filter((id) => id !== techniqueId)
      : atBudget
        ? selectedIds
        : [...selectedIds, techniqueId];
    if (next === selectedIds) return;
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          selected_technique_ids: next,
        },
      },
    });
  };

  const grouped = CATEGORY_ORDER.map((category) => ({
    category,
    label: CATEGORY_LABELS[category],
    options: options.filter((technique) => technique.category === category),
  })).filter((group) => group.options.length > 0);

  return (
    <div className="space-y-6">
      <div
        className={cn(
          'w-fit rounded-lg border px-4 py-2 text-sm font-medium',
          atBudget
            ? 'border-primary bg-primary/10 text-primary'
            : 'border-muted-foreground/30 text-muted-foreground'
        )}
      >
        {selectedIds.length} of {picks} chosen
      </div>

      {grouped.map((group) => (
        <div key={group.category} className="space-y-3">
          <h4 className="text-sm font-semibold text-muted-foreground">{group.label}</h4>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {group.options.map((technique) => {
              const isSelected = selectedIds.includes(technique.id);
              const disabled = !isSelected && atBudget;
              return (
                <Card
                  key={technique.id}
                  className={cn(
                    'transition-all',
                    disabled ? 'cursor-not-allowed opacity-50' : 'cursor-pointer',
                    isSelected && 'ring-2 ring-primary',
                    !isSelected && !disabled && 'hover:ring-1 hover:ring-primary/50'
                  )}
                  onClick={() => !disabled && toggle(technique.id)}
                >
                  <CardHeader className="space-y-1 p-3">
                    <CardTitle className="flex items-center justify-between gap-2 text-sm">
                      <span>
                        {technique.codex_entry_id != null ? (
                          <CodexTerm entryId={technique.codex_entry_id}>{technique.name}</CodexTerm>
                        ) : (
                          technique.name
                        )}
                      </span>
                      {isSelected && <CheckCircle2 className="h-4 w-4 shrink-0 text-primary" />}
                    </CardTitle>
                    {technique.is_signature && (
                      <Badge variant="outline" className="w-fit text-xs">
                        {traditionName} signature
                      </Badge>
                    )}
                  </CardHeader>
                  <CardContent className="px-3 pb-3 pt-0">
                    <CardDescription className="text-xs">{technique.description}</CardDescription>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}
