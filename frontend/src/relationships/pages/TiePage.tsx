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
 * The write blocks are gated on `tie.is_own_side`, NEVER on `audience`. `tie_audience`
 * short-circuits on staffness, so a staff account reading anyone's tie is STAFF — and
 * four of the seven writes resolve their side from the CALLER's own sheet, so a door
 * opened on the audience enum wrote a durable row on the staff character's own side.
 *
 * `/ties/new` is the same page before there is a tie — a character search and the
 * picker, nothing else. The card drawer links into it with the persona AND its name, so
 * the page can say who the tie is toward before anything is declared.
 */

import { useState } from 'react';
import { useParams, useSearchParams } from 'react-router-dom';

import '@/character_sheets/sheet.css';
import { usePersonaSearch } from '@/roster/usePersonaSearch';
import { useRosterEntryQuery } from '@/roster/queries';
import { useCharacterSheetQuery } from '@/character_sheets/queries';
import { Eyebrow, Heading, Stack } from '@/character_sheets/components/sheet/primitives';
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

  // The ink is a token set on the ROOT: `--plate-ground` and `--plate-accent` are
  // declared only by `.refsheet[data-ink=...]` and read by every part of the plate, so
  // without this attribute the plate renders with no ground at all and its near-white
  // ink lands on paper. Same default as the sheet's own page.
  const { data: ownerSheet } = useCharacterSheetQuery(entry?.character.id ?? 0);
  const ink = ownerSheet?.plate_ink ?? 'ember';

  const { data: tie, isLoading, error } = useTie(relationshipId);
  const { data: targetPersonaId = null } = useTargetPersonaId(tie?.other_sheet_id);

  if (isNew) return <DeclareTie ownerName={ownerName} ink={ink} />;

  if (error instanceof TieNotFoundError) {
    return <p className="p-4">Tie not found.</p>;
  }
  if (isLoading) return <p className="p-4">Loading...</p>;
  if (!tie) return <p className="p-4">Tie not found.</p>;

  return (
    <div className="refsheet" data-ink={ink}>
      <TiePlate
        tie={tie}
        ownerName={ownerName}
        isOwnSide={tie.is_own_side}
        targetPersonaId={targetPersonaId}
      />
      <div className="refsheet-leaf">
        <Stack wide>
          {tie.is_own_side && (
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
 *
 * The persona the writes will name is ALWAYS one the page has just printed by name. The
 * drawer passes `?persona=` and `&name=`, and the name seeds the search; the id is taken
 * from the resolved match (with `?persona=` breaking a tie between two characters of the
 * same name), never from the query string alone. So there is no arrangement in which
 * Declare writes toward somebody the player was never shown.
 */
function DeclareTie({ ownerName, ink }: { ownerName: string | null; ink: string }) {
  const [params] = useSearchParams();
  const preselectedId = params.get('persona') ? Number(params.get('persona')) : null;
  const [term, setTerm] = useState(params.get('name') ?? '');
  const { results } = usePersonaSearch(term);

  const wanted = term.trim().toLowerCase();
  const matches = wanted ? results.filter((result) => result.name.toLowerCase() === wanted) : [];
  const matched = matches.find((result) => result.id === preselectedId) ?? matches[0] ?? null;

  return (
    <div className="refsheet" data-ink={ink}>
      <div className="refsheet-leaf">
        <Stack wide>
          {matched && (
            <Stack>
              {ownerName && <Eyebrow>{ownerName} and</Eyebrow>}
              <Heading>{matched.name}</Heading>
            </Stack>
          )}
          <div className="refsheet-field">
            <label htmlFor="tie-about">About a character</label>
            <input
              id="tie-about"
              list="tie-people"
              className="refsheet-input"
              value={term}
              onChange={(event) => setTerm(event.target.value)}
            />
            <datalist id="tie-people">
              {results.map((result) => (
                <option key={result.id} value={result.name} />
              ))}
            </datalist>
          </div>
          <TypePicker target={matched ? { target_persona_id: matched.id } : {}} />
        </Stack>
      </div>
    </div>
  );
}
