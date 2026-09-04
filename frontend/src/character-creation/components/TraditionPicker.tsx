/**
 * TraditionPicker (#3630) — traditions as index entries, first step of the
 * Gift funnel.
 *
 * Reading is free (Decision 6): a tradition's full description sits in its
 * entry body, and its holder perspectives appear there too, but only once
 * it's chosen — never on hover. Wrapped by `TraditionStep`, which guards on
 * the draft having a selected Beginning.
 */

import { CodexTerm } from '@/codex/components/CodexTerm';
import { Entry, EntryDoors, EntryList, Paragraphs } from '../folio';
import { useSelectTradition, useTraditionPerspectives, useTraditions } from '../queries';
import type { CharacterDraft } from '../types';
import { PerspectivesPanel } from './PerspectivesPanel';

interface TraditionPickerProps {
  draft: CharacterDraft;
  beginningId: number;
}

export function TraditionPicker({ draft, beginningId }: TraditionPickerProps) {
  const { data: traditions, isLoading, error } = useTraditions(beginningId);
  const selectTradition = useSelectTradition();
  const { data: perspectives } = useTraditionPerspectives(draft.selected_tradition?.id);

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
            tag={tradition.required_distinction_id ? 'Requires a distinction' : 'Open to you'}
            chosen={isChosen}
            open={isChosen}
          >
            <Paragraphs text={tradition.description} />
            {isChosen && perspectives && perspectives.length > 0 && (
              <PerspectivesPanel perspectives={perspectives} />
            )}
            {tradition.codex_entry_ids.length > 0 && (
              <p className="ledger-line">
                <CodexTerm entryId={tradition.codex_entry_ids[0]}>
                  Codex: {tradition.name}
                </CodexTerm>
              </p>
            )}
            <EntryDoors
              chooseLabel={`Choose ${tradition.name}`}
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
