/**
 * Chapter the First: Origin (#3540).
 *
 * One question, then the starting realms as index entries (each the capital
 * of its realm, prose verbatim from the StartingArea row). Reading is free;
 * the realm enters when the player chooses (never on hover, Decision 6), and
 * choosing a different realm asks first because it clears the chapters that
 * depended on it. The record rail lists the choice; it says nothing else
 * (Decision 8).
 */

import { useRealmTheme } from '@/components/realm-theme-provider';
import { useEffect, useState } from 'react';
import {
  ChapterLeaf,
  ConfirmDialog,
  Entry,
  EntryDoors,
  EntryList,
  Marginalia,
  Note,
  PageTurn,
  RecordRail,
} from '../folio';
import { useCGExplanations, useStartingAreas, useUpdateDraft } from '../queries';
import { Stage, STAGE_LABELS } from '../types';
import type { CharacterDraft, StartingArea } from '../types';
import { getRealmTheme } from '../utils';

// PLACEHOLDER: a serializer field is the right home later; realm_theme is
// currently a theme key, not a display name.
const REALM_NAMES: Record<string, string> = {
  arx: 'Arx',
  umbros: 'The Umbral Empire',
  luxen: 'The Holy Republic of Luxen',
  inferna: 'The Grand Principality of Inferna',
  ariwn: 'The Kingdoms of Ariwn',
  aythirmok: 'The Northlands',
  default: '',
};

interface OriginStageProps {
  draft: CharacterDraft;
  onStageSelect: (stage: Stage) => void;
}

export function OriginStage({ draft, onStageSelect }: OriginStageProps) {
  const { data: areas, isLoading, error } = useStartingAreas();
  const { data: copy } = useCGExplanations();
  const updateDraft = useUpdateDraft();
  const { setRealmTheme } = useRealmTheme();
  const [pending, setPending] = useState<StartingArea | null>(null);

  const chosen = draft.selected_area;

  useEffect(() => {
    if (chosen) setRealmTheme(getRealmTheme(chosen));
  }, [chosen, setRealmTheme]);

  const apply = (area: StartingArea | null) => {
    if (area) setRealmTheme(getRealmTheme(area));
    const changing = chosen?.id !== area?.id;
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        selected_area_id: area?.id ?? null,
        ...(changing && {
          selected_beginnings_id: null,
          selected_species_id: null,
          family_id: null,
        }),
      },
    });
  };

  const choose = (area: StartingArea) => {
    if (chosen && chosen.id !== area.id) {
      setPending(area);
      return;
    }
    apply(area);
  };

  if (isLoading)
    return (
      <p className="ledger-line" aria-busy="true">
        Opening the record.
      </p>
    );
  if (error)
    return <p className="ledger-line">The starting realms could not be read. Try again.</p>;

  return (
    <>
      <ChapterLeaf
        stage={Stage.ORIGIN}
        title={copy?.origin_heading ?? 'Where does the story begin?'}
        aside={
          <>
            <RecordRail
              rows={[{ label: 'Origin', value: chosen?.name }]}
              ledger="One of eleven chapters begun."
            />
            <Marginalia id="note-change">
              {/* PLACEHOLDER: Apostate rewrite */}
              <Note lead="Choosing a different origin">
                clears the chapters that depended on it. The record asks first.
              </Note>
            </Marginalia>
          </>
        }
      >
        <EntryList label="Starting realms">
          {areas?.map((area) => {
            const isChosen = chosen?.id === area.id;
            const closed = !area.is_accessible;
            const realmName = REALM_NAMES[area.realm_theme] ?? REALM_NAMES.default;
            return (
              <Entry
                key={area.id}
                name={area.name}
                tag={closed ? `${realmName} · closed to you` : realmName}
                chosen={isChosen}
                closed={closed}
                open={isChosen}
              >
                {area.description.split(/\n\s*\n/).map((para, i) => (
                  <p key={i}>{para}</p>
                ))}
                {closed ? (
                  // PLACEHOLDER: Apostate rewrite; the trust threshold is not on the serializer yet
                  <p className="ledger-line">This door is closed to your account.</p>
                ) : (
                  <EntryDoors
                    chooseLabel={`Begin in ${area.name}`}
                    onChoose={() => choose(area)}
                    chosen={isChosen}
                    onSetAside={() => apply(null)}
                  />
                )}
              </Entry>
            );
          })}
        </EntryList>
        <PageTurn
          next={{
            label: `Turn the page: ${STAGE_LABELS[Stage.HERITAGE]}`,
            onClick: () => onStageSelect(Stage.HERITAGE),
            disabled: !chosen,
            reason: 'Choose a realm to turn the page.',
          }}
        />
      </ChapterLeaf>
      <ConfirmDialog
        open={pending !== null}
        title="Begin somewhere else"
        confirmLabel="Begin again there"
        cancelLabel="Keep what is written"
        onConfirm={() => {
          if (pending) apply(pending);
          setPending(null);
        }}
        onCancel={() => setPending(null)}
      >
        {/* PLACEHOLDER: Apostate rewrite */}
        The record has the story beginning in {chosen?.name}. Nothing written after Origin survives
        a new beginning.
      </ConfirmDialog>
    </>
  );
}
