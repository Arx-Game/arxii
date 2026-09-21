/**
 * One tie, opened (#3957).
 *
 * The page is ONE SIDE of a tie: the labels this character named, their depth, their
 * tier, their words. The other side's page lives on the other sheet, which is what
 * keeps this from becoming a negotiation between two players over one row.
 *
 * It decides nothing about who may see what. `useTie` either answers with a payload
 * already shaped for the viewer or 404s, and a 404 renders as NOT FOUND rather than as
 * a refusal: a tie with nothing public on it must be indistinguishable from a tie that
 * was never declared, or the shape of the error leaks the tie.
 *
 * `/ties/new` is the same page before there is a tie — a character search and the
 * picker, nothing else. The card drawer links straight into it with `?persona=`, so
 * naming someone from a scene is two clicks.
 */

import { useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';

import '@/character_sheets/sheet.css';
import { usePersonaSearch } from '@/roster/usePersonaSearch';
import { useRosterEntryQuery } from '@/roster/queries';
import { Eyebrow, Heading, Stack } from '@/character_sheets/components/sheet/primitives';
import { FIELD_INPUT_CLASS, FIELD_LABEL_CLASS } from '@/journals/fieldClasses';
import { useTargetPersonaId, useTie } from '@/relationships/queries';
import { TieNotFoundError } from '../api';
import { AdvanceTier } from '../components/AdvanceTier';
import { LabelsAndAp } from '../components/LabelsAndAp';
import { TiePlate } from '../components/TiePlate';
import { TieStream } from '../components/TieStream';
import { TypePicker } from '../components/TypePicker';

export function TiePage() {
  const { id, tieId } = useParams();
  const entryId = Number(id);
  const isNew = tieId === 'new';
  const relationshipId = isNew ? null : Number(tieId);

  const { data: entry } = useRosterEntryQuery(entryId);
  const ownerName = entry?.fullname || entry?.character.name || null;

  const { data: tie, isLoading, error } = useTie(relationshipId);
  const { data: targetPersonaId = null } = useTargetPersonaId(tie?.other_sheet_id);

  if (isNew) return <DeclareTie ownerName={ownerName} />;

  if (error instanceof TieNotFoundError) {
    return <p className="p-4">Tie not found.</p>;
  }
  if (isLoading) return <p className="p-4">Loading...</p>;
  if (!tie) return <p className="p-4">Tie not found.</p>;

  const isOwner = tie.audience === 'owner' || tie.audience === 'staff';

  return (
    <div className="refsheet">
      <TiePlate
        tie={tie}
        ownerName={ownerName}
        isOwner={isOwner}
        targetPersonaId={targetPersonaId}
      />
      <div className="refsheet-leaf">
        <Stack wide>
          {isOwner && (
            <>
              <LabelsAndAp tie={tie} targetPersonaId={targetPersonaId} />
              <AdvanceTier tie={tie} targetPersonaId={targetPersonaId} />
            </>
          )}
          {tie.other_sheet_id != null && (
            <TieStream
              tieId={tie.id}
              ownerName={ownerName ?? ''}
              otherName={tie.target_name}
              ownerSheetId={tie.source}
              otherSheetId={tie.other_sheet_id}
            />
          )}
        </Stack>
      </div>
    </div>
  );
}

/**
 * Declaring the first label toward someone who is not on the cast yet.
 *
 * The same persona type-ahead the journals composer uses to say who an entry is about,
 * for the same reason: a tie can be toward anyone, so this is a search and not a list
 * of people the character already knows.
 */
function DeclareTie({ ownerName }: { ownerName: string | null }) {
  const [params] = useSearchParams();
  const preselected = params.get('persona');
  const [term, setTerm] = useState('');
  const { results } = usePersonaSearch(term);

  const matched = results.find((result) => result.name.toLowerCase() === term.trim().toLowerCase());
  const personaId = matched?.id ?? (preselected ? Number(preselected) : null);

  return (
    <div className="refsheet">
      <div className="refsheet-leaf">
        <Stack wide>
          <Stack>
            {ownerName && <Eyebrow>{ownerName} and</Eyebrow>}
            <Heading>{matched?.name ?? 'Declare a tie'}</Heading>
          </Stack>
          <div className="grid gap-[.3rem]">
            <label className={FIELD_LABEL_CLASS} htmlFor="tie-about">
              About a character
            </label>
            <input
              id="tie-about"
              list="tie-people"
              className={FIELD_INPUT_CLASS}
              value={term}
              onChange={(event) => setTerm(event.target.value)}
            />
            <datalist id="tie-people">
              {results.map((result) => (
                <option key={result.id} value={result.name} />
              ))}
            </datalist>
          </div>
          <TypePicker target={personaId != null ? { target_persona_id: personaId } : {}} />
        </Stack>
      </div>
    </div>
  );
}
