/**
 * The stream under a tie (#3957) — everything the two of them wrote about each other,
 * and every scene they were both in.
 *
 * Drawn with the Reading Room's own row parts (`journals/components/EntryRowParts`)
 * rather than a second idea of what an entry looks like, so the two cannot drift: same
 * band, same meta line, same seven-line clamp, one spelling of "Black journal". That is
 * also why the block roots itself in `.journals` — every one of those rules is scoped
 * under it, so a row drawn outside that class renders unstyled (the #3667 lesson: assert
 * the rule REACHES the page, not that the class name is in the markup).
 *
 * The server already removed anything this viewer may not read, so the pills here only
 * ever narrow what is in hand — they are a reader's convenience, never a gate.
 */

import { useState } from 'react';

import '@/journals/journals.css';
import { PillButton } from '@/journals/components/Pill';
import { EntryBand, EntryBody, EntryMeta, EntryTitle } from '@/journals/components/EntryRowParts';
import { BLACK_JOURNAL_BAND, entryRowClass } from '@/journals/rows';
import { formatIcDate, formatPostingDate } from '@/journals/dates';
import { useTieStream } from '@/relationships/queries';
import type { TieStreamItem } from '../api';

type Slice = 'all' | 'capstones' | 'owner' | 'other' | 'scenes';

/** The first word of a name — what the pills have room for. */
function firstName(name: string): string {
  return name.trim().split(/\s+/)[0] || name;
}

function keep(item: TieStreamItem, slice: Slice, ownerSheetId: number, otherSheetId: number) {
  switch (slice) {
    case 'capstones':
      return item.is_capstone;
    case 'owner':
      return item.author_id === ownerSheetId;
    case 'other':
      return item.author_id === otherSheetId;
    case 'scenes':
      return item.kind === 'scene';
    default:
      return true;
  }
}

/** `Capstone · tier 2` where the viewer may know the tier, `Capstone` where they may not. */
function bandText(item: TieStreamItem): string | null {
  if (item.is_capstone) {
    return item.capstone_tier == null ? 'Capstone' : `Capstone · tier ${item.capstone_tier}`;
  }
  if (!item.is_public) return BLACK_JOURNAL_BAND;
  return null;
}

export interface TieStreamProps {
  tieId: number;
  /** The side owner's name, or null when the page could not confirm whose side it is. */
  ownerName: string | null;
  otherName: string;
  /** CharacterSheet pks, which is what a stream item's `author_id` is. */
  ownerSheetId: number;
  otherSheetId: number;
}

export function TieStream({
  tieId,
  ownerName,
  otherName,
  ownerSheetId,
  otherSheetId,
}: TieStreamProps) {
  const [slice, setSlice] = useState<Slice>('all');
  const { data: items = [] } = useTieStream(tieId);

  // A "By " pill with nobody after it is worse than no pill: the owner's name is only
  // known when the page confirmed whose side this is, so that one is drawn or vanishes.
  const pills: Array<{ value: Slice; label: string }> = [
    { value: 'all', label: 'Everything' },
    { value: 'capstones', label: 'Capstones' },
    ...(ownerName ? [{ value: 'owner' as Slice, label: `By ${firstName(ownerName)}` }] : []),
    { value: 'other', label: `By ${firstName(otherName)}` },
    { value: 'scenes', label: 'Scenes' },
  ];

  const shown = items.filter((item) => keep(item, slice, ownerSheetId, otherSheetId));

  return (
    <div className="journals refsheet-stream">
      <div className="flex flex-wrap gap-2 pb-2">
        {pills.map((pill) => (
          <PillButton
            key={pill.value}
            pressed={slice === pill.value}
            onClick={() => setSlice(pill.value)}
          >
            {pill.label}
          </PillButton>
        ))}
      </div>
      {shown.map((item) => {
        const band = bandText(item);
        const isScene = item.kind === 'scene';
        const date = item.ic_timestamp
          ? formatIcDate(item.ic_timestamp)
          : formatPostingDate(item.created_at);
        return (
          <article
            key={`${item.kind}-${item.id}`}
            className={entryRowClass({ isBlack: !item.is_public })}
          >
            {band && <EntryBand>{band}</EntryBand>}
            <EntryMeta who={item.author_name || undefined} date={date} />
            <EntryTitle quiet={isScene}>{item.title}</EntryTitle>
            {item.body && <EntryBody clamped>{item.body}</EntryBody>}
          </article>
        );
      })}
    </div>
  );
}
