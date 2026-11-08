/**
 * GiftFacetsField (#5021): the optional facet pick for the gift resonance, under the
 * Gift stage's Motif. Up to five facets from the staff-authored vocabulary (the shared
 * FacetPicker, no create), saved at `draft_data.selected_gift_facet_ids`. A picked facet
 * opens the flourishes gated on it in "make it yours" (the personalization options key
 * carries the picks, so they refetch), and finalize ties the picks to the gift resonance.
 */

import { X } from 'lucide-react';

import { FacetPicker } from '@/magic/components/FacetPicker';
import { useFacets, useUpdateDraft } from '../../queries';
import type { CharacterDraft } from '../../types';

/** The Motif's per-resonance cap (MotifResonanceAssociation.MAX_PER_RESONANCE). */
const MAX_FACETS = 5;

interface Props {
  draft: CharacterDraft;
  resonanceName?: string;
}

export function GiftFacetsField({ draft, resonanceName }: Props) {
  const { data: facets } = useFacets();
  const updateDraft = useUpdateDraft();
  const picked = draft.draft_data.selected_gift_facet_ids ?? [];
  const nameOf = (id: number): string => facets?.find((facet) => facet.id === id)?.name ?? '…';

  const save = (ids: number[]) =>
    updateDraft.mutate({
      draftId: draft.id,
      data: { draft_data: { selected_gift_facet_ids: ids } },
    });

  return (
    <div className="field" data-testid="gift-facets-field">
      <span className="label">{resonanceName ? `Facets of ${resonanceName}` : 'Facets'}</span>
      <div className="flex flex-wrap items-center gap-2">
        {picked.map((id) => (
          <span
            key={id}
            className="inline-flex items-center gap-1 rounded-full bg-muted px-3 py-1 text-sm"
          >
            {nameOf(id)}
            <button
              type="button"
              aria-label={`Remove ${nameOf(id)}`}
              className="text-muted-foreground hover:text-foreground"
              disabled={updateDraft.isPending}
              onClick={() => save(picked.filter((other) => other !== id))}
            >
              <X className="h-3 w-3" />
            </button>
          </span>
        ))}
        {picked.length < MAX_FACETS && (
          <FacetPicker
            facets={facets}
            exclude={picked}
            onPick={(facet) => save([...picked, facet.id])}
          />
        )}
      </div>
      <span className="hint">
        {picked.length} of {MAX_FACETS}
      </span>
    </div>
  );
}
