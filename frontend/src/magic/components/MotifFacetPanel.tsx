/**
 * MotifFacetPanel (#5021): the player ties facets (Wolf, Silk, Red) to each resonance
 * they have claimed, and unties them. Mounted in SpellbookTab beside MotifStylePanel,
 * own view only.
 *
 * Wire contract: MotifStyleViewSet (src/world/magic/views_motif_style.py). The list
 * comes from GET /api/magic/motif-styles/'s `facet_bindings`; tying and untying POST
 * bind-facet / unbind-facet, which dispatch BindMotifFacetAction /
 * UnbindMotifFacetAction (src/actions/definitions/motif_facet.py). A refusal (five
 * facets already, a signed flourish still needs the facet) comes back as `{detail}`
 * and shows verbatim. The picker is the shared FacetPicker without `canCreate`:
 * players never make new facets.
 */

import { X } from 'lucide-react';

import { Subheading, Tag } from '@/character_sheets/components/sheet/primitives';
import { useFacets } from '@/character-creation/queries';
import { FacetPicker } from '@/magic/components/FacetPicker';
import { useCharacterResonances, useMotifStyleBindings, useSetMotifFacet } from '@/magic/queries';

interface Props {
  /** CharacterSheet pk (shared with the character ObjectDB pk) of the acting character. */
  characterSheetId: number;
}

export function MotifFacetPanel({ characterSheetId }: Props) {
  const { data: bindingsData } = useMotifStyleBindings(characterSheetId);
  const { data: resonances = [] } = useCharacterResonances(characterSheetId);
  const { data: facets } = useFacets();
  const setFacet = useSetMotifFacet(characterSheetId);

  if (resonances.length === 0) return null;
  const ties = bindingsData?.facet_bindings ?? [];

  return (
    <div className="refsheet-stack-wide" data-testid="motif-facet-panel">
      <Subheading>Facets</Subheading>
      <div className="space-y-3">
        {resonances.map((cr) => {
          const tied = ties.filter((t) => t.resonance_id === cr.resonance);
          return (
            <div key={cr.resonance} data-testid={`motif-facet-group-${cr.resonance}`}>
              <Tag>{cr.resonance_name}</Tag>
              <div className="mt-1 flex flex-wrap items-center gap-2">
                {tied.map((t) => (
                  <span
                    key={t.facet_id}
                    className="inline-flex items-center gap-1 rounded-full bg-muted px-3 py-1 text-sm"
                    data-testid="motif-facet-chip"
                  >
                    {t.facet_name}
                    <button
                      type="button"
                      aria-label={`Untie ${t.facet_name}`}
                      className="text-muted-foreground hover:text-foreground disabled:opacity-50"
                      disabled={setFacet.isPending}
                      onClick={() =>
                        setFacet.mutate({
                          facet_id: t.facet_id,
                          resonance_id: cr.resonance,
                          tie: false,
                        })
                      }
                    >
                      <X className="h-3 w-3" />
                    </button>
                  </span>
                ))}
                <FacetPicker
                  facets={facets}
                  exclude={tied.map((t) => t.facet_id)}
                  onPick={(facet) =>
                    setFacet.mutate({ facet_id: facet.id, resonance_id: cr.resonance, tie: true })
                  }
                />
              </div>
            </div>
          );
        })}
      </div>
      {setFacet.isError ? (
        <p
          role="alert"
          data-testid="motif-facet-error"
          className="text-sm font-medium text-red-500"
        >
          {setFacet.error?.message}
        </p>
      ) : null}
    </div>
  );
}
