/**
 * The stream under a tie (#3957) — everything the two of them wrote about each other,
 * and every scene they were both in.
 *
 * Drawn in the Reading Room's own row shape and its own stylesheet rather than a second
 * idea of what an entry looks like: same band, same meta line, same seven-line clamp.
 * That is why the block roots itself in `.journals` — every one of those rules is
 * scoped under it, so a row drawn outside that class renders unstyled (the #3667
 * lesson: assert the rule REACHES the page, not that the class name is in the markup).
 *
 * The server already removed anything this viewer may not read, so the pills here only
 * ever narrow what is in hand — they are a reader's convenience, never a gate.
 */

import { useState } from 'react';

import '@/journals/journals.css';
import { PillButton } from '@/journals/components/Pill';
import { formatIcDate, formatPostingDate } from '@/journals/dates';
import { cn } from '@/lib/utils';
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
  if (!item.is_public) return 'Black journal';
  return null;
}

export interface TieStreamProps {
  tieId: number;
  ownerName: string;
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

  const pills: Array<{ value: Slice; label: string }> = [
    { value: 'all', label: 'Everything' },
    { value: 'capstones', label: 'Capstones' },
    { value: 'owner', label: `By ${firstName(ownerName)}` },
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
            className={cn(
              'grid gap-[.35rem] border-t py-[1.1rem] first:border-t-0 first:pt-0',
              !item.is_public && 'jr-black my-[.35rem] border-t-0 px-5'
            )}
          >
            {band && (
              <div className="jr-sans jr-soft text-[.6875rem] uppercase tracking-[.14em] text-muted-foreground">
                {band}
              </div>
            )}
            <div className="jr-sans jr-soft flex flex-wrap items-baseline gap-x-[.9rem] gap-y-1 text-[.8125rem] text-muted-foreground">
              {item.author_name && (
                <span className="jr-strong font-body text-[1.05rem] font-semibold text-foreground">
                  {item.author_name}
                </span>
              )}
              <span>{date}</span>
            </div>
            <h3
              className={cn(
                'm-0 font-body leading-[1.2]',
                isScene ? 'text-[1.1rem] italic' : 'text-[1.4rem] font-medium'
              )}
            >
              {item.title}
            </h3>
            {item.body && <div className="jr-body jr-clamp font-body">{item.body}</div>}
          </article>
        );
      })}
    </div>
  );
}
