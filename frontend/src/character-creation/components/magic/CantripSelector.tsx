/**
 * CantripSelector - Lets the player pick a starting cantrip during character creation.
 *
 * Groups cantrips by archetype, renders each as a clickable card, and shows a
 * facet dropdown when the selected cantrip requires one.
 */

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';
import { useUpdateDraft } from '../../queries';
import type { Cantrip, CharacterDraft } from '../../types';

const ARCHETYPE_LABELS: Record<Cantrip['archetype'], string> = {
  attack: 'Offense',
  defense: 'Defense',
  buff: 'Enhancement',
  debuff: 'Affliction',
  utility: 'Utility',
};

const ARCHETYPE_ORDER: Cantrip['archetype'][] = ['attack', 'defense', 'buff', 'debuff', 'utility'];

interface CantripSelectorProps {
  draft: CharacterDraft;
  cantrips: Cantrip[];
}

export function CantripSelector({ draft, cantrips }: CantripSelectorProps) {
  const updateDraft = useUpdateDraft();
  const selectedCantripId = draft.draft_data.selected_cantrip_id ?? null;
  const selectedFacetId = draft.draft_data.selected_facet_id ?? null;

  const selectedCantrip = cantrips.find((c) => c.id === selectedCantripId) ?? null;

  // Group cantrips by archetype
  const grouped = ARCHETYPE_ORDER.map((archetype) => ({
    archetype,
    label: ARCHETYPE_LABELS[archetype],
    cantrips: cantrips
      .filter((c) => c.archetype === archetype)
      .sort((a, b) => a.sort_order - b.sort_order),
  })).filter((group) => group.cantrips.length > 0);

  const handleSelectCantrip = (cantripId: number) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          ...draft.draft_data,
          selected_cantrip_id: cantripId,
          selected_facet_id: null,
        },
      },
    });
  };

  const handleSelectFacet = (facetId: string) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          ...draft.draft_data,
          selected_facet_id: parseInt(facetId, 10),
        },
      },
    });
  };

  return (
    <div className="space-y-6">
      {grouped.map((group) => (
        <div key={group.archetype} className="space-y-3">
          <h4 className="text-sm font-semibold text-muted-foreground">{group.label}</h4>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
            {group.cantrips.map((cantrip) => {
              const isSelected = selectedCantripId === cantrip.id;
              return (
                <Card
                  key={cantrip.id}
                  className={cn(
                    'cursor-pointer transition-all',
                    isSelected && 'ring-2 ring-primary',
                    !isSelected && 'hover:ring-1 hover:ring-primary/50'
                  )}
                  onClick={() => handleSelectCantrip(cantrip.id)}
                >
                  <CardHeader className="p-3">
                    <CardTitle className="text-sm">{cantrip.name}</CardTitle>
                  </CardHeader>
                  <CardContent className="px-3 pb-3 pt-0">
                    <CardDescription className="text-xs">{cantrip.description}</CardDescription>
                  </CardContent>
                </Card>
              );
            })}
          </div>
        </div>
      ))}

      {/* Facet selector for manifested cantrips */}
      {selectedCantrip?.requires_facet && selectedCantrip.allowed_facets.length > 0 && (
        <div className="max-w-xs space-y-2">
          <Label>{selectedCantrip.facet_prompt || 'Choose a facet'}</Label>
          <Select value={selectedFacetId?.toString() ?? ''} onValueChange={handleSelectFacet}>
            <SelectTrigger>
              <SelectValue placeholder="Select a facet" />
            </SelectTrigger>
            <SelectContent>
              {selectedCantrip.allowed_facets.map((facet) => (
                <SelectItem key={facet.id} value={facet.id.toString()}>
                  {facet.name}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>
      )}
    </div>
  );
}
