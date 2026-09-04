/**
 * TechniqueSelector (#3630) — techniques as index entries, third step of the
 * Gift funnel.
 *
 * Lists the technique options (pool ∪ signature) for the chosen gift, grouped
 * by category using the same Offense/Defense/Enhancement/Affliction/Utility
 * labels the old CantripSelector used for cantrip archetypes. Picks are capped
 * at `draft.starting_technique_picks` (base 1 + distinction bonus).
 */

import { useEffect } from 'react';
import { CodexTerm } from '@/codex/components/CodexTerm';
import { TechniqueEffectSummaryDisplay } from '@/magic/components/TechniqueEffectSummary';
import { Entry, EntryDoors, EntryList } from '../../folio';
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

/**
 * Toggling a technique: deselect it if it is already chosen, refuse to add when
 * the budget is spent, otherwise add it.
 */
function nextSelection(
  selectedIds: number[],
  techniqueId: number,
  isSelected: boolean,
  atBudget: boolean
): number[] {
  if (isSelected) return selectedIds.filter((id) => id !== techniqueId);
  if (atBudget) return selectedIds;
  return [...selectedIds, techniqueId];
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
      <p className="ledger-line" aria-busy="true">
        Loading techniques…
      </p>
    );
  }

  if (!options || options.length === 0) {
    return <p className="ledger-line">No techniques are available for this gift.</p>;
  }

  const atBudget = selectedIds.length >= picks;

  const toggle = (techniqueId: number) => {
    const isSelected = selectedIds.includes(techniqueId);
    const next = nextSelection(selectedIds, techniqueId, isSelected, atBudget);
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
    <div>
      <p className="ledger-line" role="status">
        {selectedIds.length} of {picks} chosen
      </p>

      {grouped.map((group) => (
        <div key={group.category}>
          <h3 className="section-h">{group.label}</h3>
          <EntryList label={`${group.label} techniques`}>
            {group.options.map((technique) => {
              const isSelected = selectedIds.includes(technique.id);
              const closed = atBudget && !isSelected;
              let tag = 'Pool';
              if (closed) {
                tag = 'Budget reached';
              } else if (technique.is_tradition_technique) {
                tag = `${traditionName} technique`;
              }
              return (
                <Entry
                  key={technique.id}
                  name={technique.name}
                  tag={tag}
                  chosen={isSelected}
                  closed={closed}
                  open={isSelected}
                >
                  <p>{technique.description}</p>
                  <TechniqueEffectSummaryDisplay
                    summary={technique.effect_summary}
                    variant="full"
                  />
                  {technique.codex_entry_id != null && (
                    <p className="ledger-line">
                      <CodexTerm entryId={technique.codex_entry_id}>
                        Codex: {technique.name}
                      </CodexTerm>
                    </p>
                  )}
                  <EntryDoors
                    chooseLabel={`Choose ${technique.name}`}
                    onChoose={() => toggle(technique.id)}
                    chosen={isSelected}
                    onSetAside={() => toggle(technique.id)}
                  />
                </Entry>
              );
            })}
          </EntryList>
        </div>
      ))}
    </div>
  );
}
