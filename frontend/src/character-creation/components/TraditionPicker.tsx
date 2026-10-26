/**
 * TraditionPicker (#3630) — traditions as index entries, first step of the
 * Gift funnel.
 *
 * Reading is free (Decision 6): a tradition's full description sits in its
 * entry body, and its holder perspectives appear there too, but only once
 * it's chosen — never on hover. The body also names the Gifts and affinities
 * the tradition teaches well (#4659). Wrapped by `TraditionStep`, which guards on
 * the draft having a selected Beginning.
 */

import { CodexLine, Entry, EntryDoors, EntryList, Paragraphs } from '../folio';
import {
  useCGExplanations,
  useSelectTradition,
  useTraditionPerspectives,
  useTraditions,
} from '../queries';
import type { CGExplanations, CharacterDraft, Tradition } from '../types';
import { SchoolingStances } from './offers/SchoolingStances';
import { PerspectivesPanel } from './PerspectivesPanel';

interface TraditionPickerProps {
  draft: CharacterDraft;
  beginningId: number;
}

/**
 * The refund/cost bite appended to a tradition's state line, if any:
 * `refund` is the carried drawback's `cost_per_rank` (negative = the player
 * is refunded points, positive = the tradition costs points to join).
 */
function bite(refund: number): string {
  if (refund === 0) return '';
  return refund < 0 ? ` · Awards ${-refund}` : ` · ${refund}`;
}

function tagFor(tradition: Tradition): string {
  return `${tradition.state_line}${bite(tradition.refund)}`;
}

/**
 * The Gifts and affinities a Tradition teaches well (#4659): its gift grant rows and
 * favored affinities, as tags. Nothing when it favors neither.
 */
function TeachesWell({ tradition, copy }: { tradition: Tradition; copy?: CGExplanations }) {
  const gifts = tradition.favored_gift_names ?? [];
  const affinities = tradition.favored_affinity_names ?? [];
  if (gifts.length === 0 && affinities.length === 0) return null;
  return (
    <p className="ledger-line">
      {copy?.gift_teaches_well ?? 'Teaches well'}
      {gifts.length > 0 && (
        <>
          {' · '}
          {copy?.gift_teaches_well_gifts ?? 'Gifts:'}{' '}
          <span className="tags">
            {gifts.map((name) => (
              <span key={name} className="tag">
                {name}
              </span>
            ))}
          </span>
        </>
      )}
      {affinities.length > 0 && (
        <>
          {' · '}
          {copy?.gift_teaches_well_affinities ?? 'Affinity:'}{' '}
          <span className="tags">
            {affinities.map((name) => (
              <span key={name} className="tag">
                {name}
              </span>
            ))}
          </span>
        </>
      )}
    </p>
  );
}

export function TraditionPicker({ draft, beginningId }: TraditionPickerProps) {
  const { data: traditions, isLoading, error } = useTraditions(beginningId);
  const selectTradition = useSelectTradition();
  const { data: perspectives } = useTraditionPerspectives(draft.selected_tradition?.id);
  const { data: copy } = useCGExplanations();

  const handleSelect = (traditionId: number) => {
    if (selectTradition.isPending) return;
    selectTradition.mutate({ draftId: draft.id, traditionId });
  };

  const handleClear = () => {
    selectTradition.mutate({ draftId: draft.id, traditionId: null });
  };

  if (isLoading) {
    return (
      <p className="ledger-line" aria-busy="true">
        Loading traditions…
      </p>
    );
  }

  if (error) {
    return <p className="ledger-line">The traditions could not be read. Try again.</p>;
  }

  if (!traditions || traditions.length === 0) {
    return <p className="ledger-line">No traditions are available for this beginning.</p>;
  }

  return (
    <EntryList label="Traditions">
      {traditions.map((tradition) => {
        const isChosen = draft.selected_tradition?.id === tradition.id;
        return (
          <Entry
            key={tradition.id}
            name={tradition.name}
            tag={tagFor(tradition)}
            chosen={isChosen}
            open={isChosen}
            onChoose={() => handleSelect(tradition.id)}
            onSetAside={handleClear}
          >
            <Paragraphs text={tradition.description} />
            <TeachesWell tradition={tradition} copy={copy} />
            {isChosen && perspectives && perspectives.length > 0 && (
              // `.note` is scoped to `.note-group` in cg.css, so a bare panel
              // here would render unstyled; this is Marginalia's own markup.
              <div className="note-group">
                <PerspectivesPanel perspectives={perspectives} />
              </div>
            )}
            {/* The server decides which states open stances (living masters: ranks 0-2,
                teachers gone: 0-1, self-taught: none), so the field follows the rows. */}
            {isChosen && tradition.schooling.length > 0 && (
              <div className="field">
                <label>
                  {(copy?.gift_schooling_label ?? 'How you came to {tradition}').replace(
                    '{tradition}',
                    tradition.name
                  )}
                </label>
                <SchoolingStances draft={draft} tradition={tradition} copy={copy} />
              </div>
            )}
            <CodexLine entryId={tradition.codex_entry_ids?.[0]} name={tradition.name} />
            <EntryDoors
              chooseLabel={`Select ${tradition.name}`}
              onChoose={() => handleSelect(tradition.id)}
              chosen={isChosen}
              onSetAside={handleClear}
            />
          </Entry>
        );
      })}
    </EntryList>
  );
}
