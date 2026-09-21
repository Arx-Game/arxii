/**
 * Advance Relationship Tier (#3957) — the claim, against a capstone entry and XP.
 *
 * The capstone is not a second piece of prose to write: it is a journal entry this
 * character already wrote about the other one, which is why the search here is over
 * the owner's own entries filtered to that subject rather than a composer.
 *
 * Absent entirely at the top tier — `next_tier_threshold` null means there is nothing
 * left to claim, and a disabled button would be the page apologising for that.
 *
 * The XP cost is not on the tie payload (it comes from the growth config singleton), so
 * the hover repeats the rule the one line under the door states: ten per tier level.
 */

import { useState } from 'react';

import { useJournalEntries } from '@/journals/queries';
import { Eyebrow, QuietDoor } from '@/character_sheets/components/sheet/primitives';
import { useAdvanceTier } from '@/relationships/queries';
import { tieTargetRef, type Tie } from '../api';

/** The placeholder ladder's cost: ten XP times the tier being claimed. */
function xpCost(tie: Tie): number {
  return 10 * ((tie.breakdown?.tier ?? 0) + 1);
}

export interface AdvanceTierProps {
  tie: Tie;
  targetPersonaId: number | null;
}

export function AdvanceTier({ tie, targetPersonaId }: AdvanceTierProps) {
  const advance = useAdvanceTier();
  const [term, setTerm] = useState('');
  const [picked, setPicked] = useState<{ id: number; title: string } | null>(null);
  const [error, setError] = useState<string | null>(null);

  // The owner's own entries about the other side — public and black alike, since the
  // author is the viewer and the feed's visibility rule already says so.
  const { data } = useJournalEntries({
    author: tie.source,
    about: tie.other_sheet_id ?? undefined,
    page_size: 50,
  });

  if (tie.next_tier_threshold == null || tie.depth == null) return null;

  const entries = (data?.results ?? []).filter((entry) =>
    term.trim() ? entry.title.toLowerCase().includes(term.trim().toLowerCase()) : true
  );
  const reached = tie.depth >= tie.next_tier_threshold;

  function submit() {
    if (!picked) return;
    setError(null);
    advance.mutate(
      { ...tieTargetRef(tie, targetPersonaId), journal_entry_id: picked.id },
      {
        onSuccess: () => setPicked(null),
        onError: (err: Error) => setError(err.message),
      }
    );
  }

  return (
    <div className="refsheet-block">
      <Eyebrow>Advance Relationship Tier</Eyebrow>
      <p className="refsheet-ledger">
        <span>
          {tie.depth} / {tie.next_tier_threshold}
        </span>
      </p>
      <div className="refsheet-field">
        <label htmlFor="capstone-pick">Capstone entry</label>
        <input
          id="capstone-pick"
          type="search"
          className="refsheet-input"
          value={picked ? picked.title : term}
          onChange={(event) => {
            setPicked(null);
            setTerm(event.target.value);
          }}
        />
      </div>
      {!picked && entries.length > 0 && (
        <div className="refsheet-doors">
          {entries.slice(0, 8).map((entry) => (
            <QuietDoor
              key={entry.id}
              onClick={() => setPicked({ id: entry.id, title: entry.title })}
            >
              {entry.title}
            </QuietDoor>
          ))}
        </div>
      )}
      {error && (
        <p role="alert" className="refsheet-note refsheet-error">
          {error}
        </p>
      )}
      <div className="refsheet-doors">
        <QuietDoor
          onClick={submit}
          title={`${xpCost(tie)} XP`}
          disabled={!reached || !picked || advance.isPending}
        >
          Advance
        </QuietDoor>
        <span className="refsheet-note">Cost: 10xp * tier level.</span>
      </div>
    </div>
  );
}
