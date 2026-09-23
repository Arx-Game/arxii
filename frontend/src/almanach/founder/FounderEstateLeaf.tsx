/**
 * FounderEstateLeaf (#3983 Plan B Task 6, plate F-V "The Estate") — the
 * house's residence in the realm's capital: a name input, district/rooms as
 * labeled dashes (both staff-set on review/the grid phase per the plate's
 * own caption — nothing here can author either), and a prose textarea.
 * Every field writes straight to the founder draft (`set`), same as
 * `FounderHouseChapter` — no per-field Save, only the savebar's Next.
 */
import { DISTRICT, DRAFT_NOTE } from '../copy';
import { useCharter } from '../queries';

import type { FounderDraft, UseFounderDraftResult } from './founderDraft';

export interface FounderEstateLeafProps {
  draft: FounderDraft;
  set: UseFounderDraftResult['set'];
  realmId: number;
  onNext: () => void;
}

export function FounderEstateLeaf({ draft, set, realmId, onNext }: FounderEstateLeafProps) {
  const { data: charter } = useCharter(realmId);

  return (
    <main className="chapter">
      <h3>
        Estate <span className="tier">{charter?.capital_name ?? ''}</span>
      </h3>
      <div className="row3">
        <div className="field">
          <label htmlFor="founder-estate-name">name</label>
          <input
            id="founder-estate-name"
            type="text"
            value={draft.estate_name}
            onChange={(event) => set('estate_name', event.target.value)}
          />
        </div>
        <div className="field">
          <span className="label">{DISTRICT}</span>
          <div className="val">
            <abbr title="none">—</abbr>
          </div>
        </div>
        <div className="field">
          <span className="label">rooms</span>
          <div className="val">
            <abbr title="none">—</abbr>
          </div>
        </div>
      </div>
      <div className="field">
        <label htmlFor="founder-estate-prose">the estate, in your words</label>
        <textarea
          id="founder-estate-prose"
          className="prose"
          value={draft.estate_description}
          onChange={(event) => set('estate_description', event.target.value)}
        />
      </div>
      <div className="savebar">
        <span className="note">{DRAFT_NOTE}</span>
        <button type="button" className="btn" onClick={onNext}>
          Next
        </button>
      </div>
    </main>
  );
}
