/**
 * What you fill in to write an entry (#3941) — which journal, the title, the
 * text, who it is about, its tags, and (black only) what happens to it after
 * your death.
 *
 * Fields only: no buttons, no posting, no dialog. The desk at the top of the
 * stream and the composer dialog the sidebar opens both render this, so the two
 * surfaces cannot drift into asking for different things.
 *
 * No help text anywhere, by ruling. "White journal · Public" and "Black journal
 * · Private" say what they are; a paragraph explaining them would be the
 * interface talking about itself.
 *
 * About is a name, not an id: the writer types a character and it resolves
 * through the persona type-ahead (`usePersonaSearch`, the same debounced,
 * race-safe search the scene and event forms use) to the CharacterSheet the
 * backend wants. An entry can be about anyone, so this is a search and not a
 * list of the writer's own roster.
 *
 * The resolution is derived from the term and the results together, and re-derived
 * whenever either moves. Resolving once, as the writer typed, meant the answer was
 * computed against results that had not arrived yet: the name looked accepted and the
 * entry posted with no subject at all.
 */
import { useEffect, useId, useMemo, useRef, useState } from 'react';

import { usePersonaSearch } from '@/roster/usePersonaSearch';
import { cn } from '@/lib/utils';

import type { PosthumousOverride } from '../api';
import type { JournalEntryFieldsValue } from '../entryFields';
import { FIELD_INPUT_CLASS, FIELD_LABEL_CLASS } from '../fieldClasses';
import { PillButton } from './Pill';

export interface JournalEntryFieldsProps {
  value: JournalEntryFieldsValue;
  onChange: (value: JournalEntryFieldsValue) => void;
  /** Whether this surface offers the after-death choice at all (it shows for a black entry). */
  showAfterDeath?: boolean;
}

export function JournalEntryFields({ value, onChange, showAfterDeath }: JournalEntryFieldsProps) {
  const ids = useId();
  const [tagDraft, setTagDraft] = useState('');
  const { results } = usePersonaSearch(value.aboutTerm);

  // A typed name is somebody only on an exact match against what the search has
  // answered with so far; both sides move, so this is derived, never latched.
  const match = useMemo(() => {
    const wanted = value.aboutTerm.trim().toLowerCase();
    if (!wanted) return null;
    return results.find((result) => result.name.toLowerCase() === wanted) ?? null;
  }, [value.aboutTerm, results]);
  const matchSheetId = match?.character_sheet ?? null;
  const matchName = match?.name ?? '';

  // The effect fires on the resolution changing, never on the rest of the form
  // moving, so the deps are the two primitives that describe it and the current
  // value is read through a ref.
  const latest = useRef({ value, onChange });
  useEffect(() => {
    latest.current = { value, onChange };
  });
  useEffect(() => {
    const { value: current, onChange: emit } = latest.current;
    if ((current.about?.id ?? null) === matchSheetId) return;
    emit({
      ...current,
      about: matchSheetId === null ? null : { id: matchSheetId, name: matchName },
    });
  }, [matchSheetId, matchName]);

  function addTagFromDraft() {
    const tag = tagDraft.trim();
    if (!tag) return;
    setTagDraft('');
    if (value.tags.includes(tag)) return;
    onChange({ ...value, tags: [...value.tags, tag] });
  }

  function handleTagKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (event.key === 'Enter') {
      event.preventDefault();
      addTagFromDraft();
      return;
    }
    if (event.key === 'Backspace' && tagDraft === '' && value.tags.length > 0) {
      onChange({ ...value, tags: value.tags.slice(0, -1) });
    }
  }

  return (
    <div className="grid gap-5">
      <div className="flex flex-wrap gap-2" role="group" aria-label="Which journal">
        <PillButton pressed={value.isPublic} onClick={() => onChange({ ...value, isPublic: true })}>
          White journal · Public
        </PillButton>
        <PillButton
          pressed={!value.isPublic}
          onClick={() => onChange({ ...value, isPublic: false })}
          className={cn(!value.isPublic && 'border-[#38302a] bg-[#1f1a17] text-[#e3dccd]')}
        >
          Black journal · Private
        </PillButton>
      </div>

      <div className="grid gap-[.3rem]">
        <label className={FIELD_LABEL_CLASS} htmlFor={`${ids}-title`}>
          Title
        </label>
        <input
          id={`${ids}-title`}
          className={FIELD_INPUT_CLASS}
          value={value.title}
          onChange={(event) => onChange({ ...value, title: event.target.value })}
        />
      </div>

      <div className="grid gap-[.3rem]">
        <label className={FIELD_LABEL_CLASS} htmlFor={`${ids}-body`}>
          Entry
        </label>
        <textarea
          id={`${ids}-body`}
          className={cn(FIELD_INPUT_CLASS, 'min-h-[12rem] resize-y leading-[1.6]')}
          value={value.body}
          onChange={(event) => onChange({ ...value, body: event.target.value })}
        />
      </div>

      <div className="grid gap-5 sm:grid-cols-2 sm:gap-x-10">
        <div className="grid gap-[.3rem]">
          <label className={FIELD_LABEL_CLASS} htmlFor={`${ids}-about`}>
            About a character
          </label>
          <input
            id={`${ids}-about`}
            list={`${ids}-people`}
            className={FIELD_INPUT_CLASS}
            value={value.aboutTerm}
            onChange={(event) => onChange({ ...value, aboutTerm: event.target.value })}
          />
          <datalist id={`${ids}-people`}>
            {results.map((result) => (
              <option key={result.id} value={result.name} />
            ))}
          </datalist>
        </div>

        <div className="grid gap-[.3rem]">
          <label className={FIELD_LABEL_CLASS} htmlFor={`${ids}-tags`}>
            Tags
          </label>
          {value.tags.length > 0 ? (
            <div className="flex flex-wrap gap-1.5" data-testid="journal-tag-list">
              {value.tags.map((tag) => (
                <span
                  key={tag}
                  className="jr-sans jr-chip flex items-center gap-1 rounded-full border px-[.55rem] py-[.05rem] text-[.75rem] text-muted-foreground"
                >
                  {tag}
                  <button
                    type="button"
                    aria-label={`Remove tag ${tag}`}
                    onClick={() =>
                      onChange({ ...value, tags: value.tags.filter((t) => t !== tag) })
                    }
                    className="cursor-pointer border-0 bg-transparent px-1 text-inherit"
                  >
                    ×
                  </button>
                </span>
              ))}
            </div>
          ) : null}
          <input
            id={`${ids}-tags`}
            className={FIELD_INPUT_CLASS}
            value={tagDraft}
            onChange={(event) => setTagDraft(event.target.value)}
            onKeyDown={handleTagKeyDown}
            onBlur={addTagFromDraft}
          />
        </div>
      </div>

      {showAfterDeath && !value.isPublic ? (
        <div className="grid gap-[.3rem]">
          <label className={FIELD_LABEL_CLASS} htmlFor={`${ids}-death`}>
            After your death
          </label>
          <select
            id={`${ids}-death`}
            className={FIELD_INPUT_CLASS}
            value={value.posthumousOverride}
            onChange={(event) =>
              onChange({ ...value, posthumousOverride: event.target.value as PosthumousOverride })
            }
          >
            <option value="inherit">Your journal&apos;s setting</option>
            <option value="reveal">Reveal</option>
            <option value="seal">Remain sealed</option>
          </select>
        </div>
      ) : null}
    </div>
  );
}
