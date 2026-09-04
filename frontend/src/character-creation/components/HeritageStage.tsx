/**
 * Stage 2: Heritage (#3630).
 *
 * Beginnings, species, and gender as index entries: reading is free, and an
 * option enters the draft only when the player chooses it (never on hover,
 * Decision 6). A parent species with subspecies is a door to a nested list of
 * its children, not a choice on its own; a leaf species is choosable. Choosing
 * a different beginnings clears the species pick, since the new beginnings
 * may not allow the one already chosen. The record rail lists the choices; it
 * explains nothing (Decision 8).
 *
 * Family selection has moved to LineageStage (Stage 3). Pronouns are
 * auto-derived at finalization. Age is set in AppearanceStage.
 */

import {
  ChapterLeaf,
  ChoiceRow,
  CodexLine,
  Entry,
  EntryDoors,
  EntryList,
  Marginalia,
  Note,
  Paragraphs,
  RecordRail,
} from '../folio';
import {
  useBeginnings,
  useBeginningsPerspectives,
  useCGExplanations,
  useCGPointBudget,
  useGenders,
  useSpecies,
  useUpdateDraft,
} from '../queries';
import type { Beginnings, CharacterDraft, Species } from '../types';
import { Stage } from '../types';
import { PerspectivesPanel } from './PerspectivesPanel';

interface HeritageStageProps {
  draft: CharacterDraft;
  onStageSelect: (stage: Stage) => void;
}

/** The cost line for a Beginnings option, plain and unhedged. */
function costTag(cost: number): string {
  return cost === 0 ? 'No cost' : `${cost} CG points`;
}

/**
 * A species' stat bonuses as a gloss line (e.g. "+1 strength, −1 wits").
 * Empty when the species carries no bonuses.
 */
function formatStatBonuses(bonuses: Record<string, number>): string {
  return Object.entries(bonuses)
    .filter(([, value]) => value !== 0)
    .map(([stat, value]) => `${value > 0 ? '+' : '−'}${Math.abs(value)} ${stat}`)
    .join(', ');
}

type SpeciesEntryItem =
  | { kind: 'leaf'; species: Species }
  | { kind: 'group'; parentId: number; name: string; children: Species[] };

export function HeritageStage({ draft, onStageSelect }: HeritageStageProps) {
  const updateDraft = useUpdateDraft();
  const { data: copy } = useCGExplanations();
  const { data: cgBudget } = useCGPointBudget();
  const { data: beginnings, isLoading: beginningsLoading } = useBeginnings(draft.selected_area?.id);
  const { data: allSpecies, isLoading: speciesLoading } = useSpecies();
  const { data: genders, isLoading: gendersLoading } = useGenders();
  const { data: perspectives } = useBeginningsPerspectives(draft.selected_beginnings?.id);

  const remaining = draft.cg_points_remaining;
  const starting = cgBudget?.starting_points ?? 100;

  // Species allowed by the selected beginnings (unchanged filter:
  // allowed_species_ids only ever lists leaves, never a parent "hub").
  const allowedIds = draft.selected_beginnings?.allowed_species_ids;
  const filteredSpecies = allSpecies?.filter((species) => allowedIds?.includes(species.id));

  // Group into standalones (no parent) and parent groups (with subspecies).
  // A parent group is synthesized from its children's parent/parent_name
  // fields, not a separate Species row — the API never returns a selectable
  // "hub" species alongside its own subspecies in the allowed set.
  const standalones: Species[] = [];
  const parentGroups = new Map<number, { name: string; children: Species[] }>();
  for (const species of filteredSpecies ?? []) {
    if (!species.parent) {
      standalones.push(species);
      continue;
    }
    const group = parentGroups.get(species.parent);
    if (group) {
      group.children.push(species);
    } else {
      parentGroups.set(species.parent, {
        name: species.parent_name ?? 'Unknown',
        children: [species],
      });
    }
  }
  const topLevel: SpeciesEntryItem[] = [
    ...standalones.map((species): SpeciesEntryItem => ({ kind: 'leaf', species })),
    ...Array.from(parentGroups.entries()).map(
      ([parentId, group]): SpeciesEntryItem => ({ kind: 'group', parentId, ...group })
    ),
  ];

  // If no area selected, prompt user to go back.
  if (!draft.selected_area) {
    return (
      <>
        <p className="ledger-line">Please select a starting area first.</p>
        <button type="button" className="btn-quiet" onClick={() => onStageSelect(Stage.ORIGIN)}>
          Go to Origin Selection
        </button>
      </>
    );
  }

  const loading = beginningsLoading || speciesLoading || gendersLoading;
  if (loading)
    return (
      <p className="ledger-line" aria-busy="true">
        Loading heritage…
      </p>
    );

  const chooseBeginning = (b: Beginnings) => {
    updateDraft.mutate({
      draftId: draft.id,
      data: { selected_beginnings_id: b.id, selected_species_id: null },
    });
  };

  const clearBeginning = () => {
    updateDraft.mutate({
      draftId: draft.id,
      data: { selected_beginnings_id: null, selected_species_id: null },
    });
  };

  const chooseSpecies = (id: number) => {
    updateDraft.mutate({ draftId: draft.id, data: { selected_species_id: id } });
  };

  // The same null the beginnings doors already write on a beginnings change,
  // so the species pick has a Clear door of its own rather than being
  // changeable only by picking a different species.
  const clearSpecies = () => {
    updateDraft.mutate({ draftId: draft.id, data: { selected_species_id: null } });
  };

  const renderLeafSpecies = (s: Species) => {
    const isChosen = draft.selected_species?.id === s.id;
    const overBudget = remaining < 0 && !isChosen;
    const gloss = formatStatBonuses(s.stat_bonuses) || undefined;
    return (
      <Entry
        key={s.id}
        name={s.name}
        gloss={gloss}
        tag={overBudget ? 'CG points overspent' : 'Available'}
        chosen={isChosen}
        closed={overBudget}
        open={isChosen}
      >
        <Paragraphs text={s.description} />
        <CodexLine entryId={s.codex_entry_id} name={s.name} />
        {!overBudget && (
          <EntryDoors
            chooseLabel={`Choose ${s.name}`}
            onChoose={() => chooseSpecies(s.id)}
            chosen={isChosen}
            onSetAside={clearSpecies}
          />
        )}
      </Entry>
    );
  };

  const renderSpeciesEntry = (item: SpeciesEntryItem) => {
    if (item.kind === 'leaf') return renderLeafSpecies(item.species);
    // A closed parent tells you which of its kinds you chose, so the pick is
    // legible without opening the group.
    const chosenChild = item.children.find(
      (child) => child.id === draft.selected_species?.id
    )?.name;
    return (
      <Entry
        key={`parent-${item.parentId}`}
        name={item.name}
        gloss={chosenChild}
        tag={`${item.children.length} kinds`}
        chosen={false}
        closed
      >
        <EntryList label={`${item.name} kinds`}>{item.children.map(renderLeafSpecies)}</EntryList>
      </Entry>
    );
  };

  const rail = (
    <>
      <RecordRail
        rows={[
          { label: 'Origin', value: draft.selected_area.name },
          { label: 'Beginnings', value: draft.selected_beginnings?.name },
          { label: 'Species', value: draft.selected_species?.name },
          { label: 'Gender', value: draft.selected_gender?.display_name },
          { label: 'CG points', value: `${draft.cg_points_spent} of ${starting} spent` },
        ]}
        ledger="Stage 2 of 11"
      />
      <Marginalia id="note-heritage">
        {perspectives && perspectives.length > 0 ? (
          <PerspectivesPanel perspectives={perspectives} />
        ) : (
          // PLACEHOLDER: Apostate rewrite
          <Note lead="Beginnings">set which species and families are open to you.</Note>
        )}
      </Marginalia>
    </>
  );

  return (
    <ChapterLeaf
      stage={Stage.HERITAGE}
      title={copy?.heritage_heading ?? 'Your Heritage'}
      intro={copy?.heritage_intro}
      aside={rail}
    >
      {copy?.heritage_lore_intro && (
        <div className="leaf-body">
          <p>{copy.heritage_lore_intro}</p>
        </div>
      )}

      <h2 className="section-h" id="beginnings">
        {copy?.heritage_beginnings_heading ?? 'Beginnings'}
      </h2>
      {copy?.heritage_beginnings_desc && (
        <p className="section-desc">{copy.heritage_beginnings_desc}</p>
      )}
      <EntryList label="Beginnings">
        {beginnings?.map((b) => {
          const isChosen = draft.selected_beginnings?.id === b.id;
          const closed = !b.is_accessible;
          return (
            <Entry
              key={b.id}
              name={b.name}
              tag={closed ? 'Not available to your account' : costTag(b.cg_point_cost)}
              chosen={isChosen}
              closed={closed}
              open={isChosen}
            >
              {/* Decorative: the entry name beside it is the text. */}
              {b.art_image && <img className="entry-art" src={b.art_image} alt="" />}
              <Paragraphs text={b.description} />
              {!b.family_known && <p className="ledger-line">Family unknown at the start.</p>}
              <CodexLine entryId={b.codex_entry_ids?.[0]} name={b.name} />
              {!closed && (
                <EntryDoors
                  chooseLabel={`Choose ${b.name}`}
                  onChoose={() => chooseBeginning(b)}
                  chosen={isChosen}
                  onSetAside={clearBeginning}
                />
              )}
            </Entry>
          );
        })}
      </EntryList>

      {draft.selected_beginnings && (
        <>
          <h2 className="section-h" id="species">
            {copy?.heritage_species_heading ?? 'Species'}
          </h2>
          {copy?.heritage_species_desc && (
            <p className="section-desc">{copy.heritage_species_desc}</p>
          )}
          <EntryList label="Species">{topLevel.map(renderSpeciesEntry)}</EntryList>
        </>
      )}

      <h2 className="section-h" id="gender">
        {copy?.heritage_gender_heading ?? 'Gender'}
      </h2>
      <ChoiceRow
        label="Gender"
        options={(genders ?? []).map((g) => ({ value: g.id, label: g.display_name }))}
        value={draft.selected_gender?.id ?? null}
        onChange={(id) => {
          if (id !== null) {
            updateDraft.mutate({ draftId: draft.id, data: { selected_gender_id: id } });
          }
        }}
      />
      <p className="ledger-line">
        Pronouns will be derived from your gender choice. You can customize them in-game.
      </p>
    </ChapterLeaf>
  );
}
