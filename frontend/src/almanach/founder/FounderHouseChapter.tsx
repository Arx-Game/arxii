/**
 * FounderHouseChapter (#3983 Plan B Task 5, plate F-II "The House") — the
 * founder's own house charter: name (live-validated against the picked
 * template's `name_pattern`), the styled-name preview, succession, words/
 * colors/sigil/backstory, the House Quiddity pick (the template's first
 * aspect definition — a founder Charter authors exactly one, unlike a name-
 * path Family Template which can carry several), and the six principle
 * axes windowed to the template's own min/max. Every field writes straight
 * to the founder draft (`set`) — there is no per-field Save here, only the
 * savebar's Next (plate: "draft kept as you type").
 *
 * Succession renders as a plain name + codex link, without the plate's own
 * `.tip`/`.bub` gloss: `SuccessionLawOption`/`AlmanachSuccessionLaw`
 * (`src/generated/api.d.ts`) carry only `{name, codex_entry_id}`, no gloss
 * text to put in a bubble — `FounderAlmanach.tsx`'s `LiegeRealmAside`
 * already hit this same gap on the Seat step and made the same call (see
 * its own comment there). `useCharter(realmId)` is read only for its
 * `particle` pair (the styled-name gloss) — its `quiddity_prompt` is the
 * REALM's tier-less default template's own prompt
 * (`charter_for_realm`, `almanach_reads.py`), a pre-selection preview for a
 * different (not-yet-built) consumer, not this chapter's own picked
 * template's prompt; see the task report.
 */
import { useId } from 'react';

import type { HouseTemplateOption } from '@/character-creation/api';

import { DRAFT_NOTE } from '../copy';
import { tierNoun } from '../ladder/tree';
import { useCharter } from '../queries';

import type { FounderDraft, UseFounderDraftResult } from './founderDraft';

export interface FounderHouseChapterProps {
  draft: FounderDraft;
  set: UseFounderDraftResult['set'];
  template: HouseTemplateOption;
  seatName: string;
  seatTier: string;
  realmId: number;
  /** The founder's own given name, once `CharacterDraft` carries a name
   * field for this chapter to read — today it doesn't (`character-creation/
   * types.ts`), so every caller passes the literal `'Given name'` (see the
   * task report). */
  youName: string;
  onNext: () => void;
}

interface PrincipleAxis {
  key: 'mercy' | 'method' | 'status' | 'change' | 'allegiance' | 'power';
  left: string;
  right: string;
  minKey: keyof HouseTemplateOption;
  maxKey: keyof HouseTemplateOption;
}

const AXES: PrincipleAxis[] = [
  {
    key: 'mercy',
    left: 'Ruthlessness',
    right: 'Compassion',
    minKey: 'mercy_min',
    maxKey: 'mercy_max',
  },
  { key: 'method', left: 'Cunning', right: 'Honor', minKey: 'method_min', maxKey: 'method_max' },
  {
    key: 'status',
    left: 'Ambition',
    right: 'Humility',
    minKey: 'status_min',
    maxKey: 'status_max',
  },
  {
    key: 'change',
    left: 'Tradition',
    right: 'Progress',
    minKey: 'change_min',
    maxKey: 'change_max',
  },
  {
    key: 'allegiance',
    left: 'Loyalty',
    right: 'Independence',
    minKey: 'allegiance_min',
    maxKey: 'allegiance_max',
  },
  { key: 'power', left: 'Hierarchy', right: 'Equality', minKey: 'power_min', maxKey: 'power_max' },
];

/** `name_pattern` is documented as a full-match regex (`HouseTemplateOption`,
 * `src/generated/api.d.ts`) — wrapped in `^(?:…)$` regardless, so an
 * authored pattern that forgot its own anchors still full-matches rather
 * than merely finding a substring. An unparsable PLACEHOLDER pattern never
 * blocks the founder (the field is seed content staff can still be
 * drafting; see `django_notes.md`'s no-management-commands-shaped caution
 * against inventing validation the backend doesn't itself enforce yet). */
function nameFitsPattern(name: string, pattern: string | undefined): boolean {
  if (!pattern) return true;
  try {
    return new RegExp(`^(?:${pattern})$`).test(name);
  } catch {
    return true;
  }
}

export function FounderHouseChapter({
  draft,
  set,
  template,
  seatName,
  seatTier,
  realmId,
  youName,
  onNext,
}: FounderHouseChapterProps) {
  const { data: charter } = useCharter(realmId);
  const nameGlossId = useId();

  const nameOk = nameFitsPattern(draft.house_name, template.name_pattern);
  const particle =
    draft.founder_relation === 'spouse' ? charter?.particle.taken_in : charter?.particle.born;
  const styledName = charter
    ? `${youName} ${particle ?? ''} ${draft.house_name}`.replace(/\s+/g, ' ').trim()
    : '';

  const quiddity = template.aspect_definitions[0];
  const quiddityPicks = quiddity ? (draft.aspect_picks[quiddity.id] ?? []) : [];

  const toggleQuiddityOption = (optionId: number, maxPicks: number) => {
    if (!quiddity) return;
    let next: number[];
    if (quiddityPicks.includes(optionId)) {
      next = quiddityPicks.filter((id) => id !== optionId);
    } else if (maxPicks === 1) {
      next = [optionId];
    } else if (quiddityPicks.length >= maxPicks) {
      return;
    } else {
      next = [...quiddityPicks, optionId];
    }
    set('aspect_picks', { ...draft.aspect_picks, [quiddity.id]: next });
  };

  return (
    <main className="chapter">
      <h3>
        House {draft.house_name}{' '}
        <span className="tier">
          {tierNoun(seatTier, 1)} of {seatName}
        </span>
      </h3>
      <div className="row3">
        <div className="field">
          <label htmlFor="founder-house-name">name</label>
          <input
            id="founder-house-name"
            type="text"
            value={draft.house_name}
            onChange={(event) => set('house_name', event.target.value)}
          />
          {draft.house_name !== '' && !nameOk && (
            <span className="chip">does not fit the realm&apos;s rule</span>
          )}
        </div>
        <div className="field">
          <span className="label">your name will read</span>
          <div className="val">
            {styledName !== '' ? (
              <button type="button" className="tip" aria-describedby={nameGlossId}>
                {styledName}
                <span className="bub" id={nameGlossId}>
                  {charter?.particle.born} for those born to the house ·{' '}
                  {charter?.particle.taken_in} for those who marry in
                </span>
              </button>
            ) : (
              <abbr title="none">—</abbr>
            )}
          </div>
        </div>
        <div className="field">
          <span className="label">succession</span>
          <div className="val">
            {template.default_succession_law ? (
              <>
                {template.default_succession_law.name}
                {template.default_succession_law.codex_entry_id != null && (
                  <>
                    {' '}
                    · <a href={`/codex/${template.default_succession_law.codex_entry_id}`}>codex</a>
                  </>
                )}
              </>
            ) : (
              <abbr title="none">—</abbr>
            )}
          </div>
        </div>
      </div>
      <div className="row2">
        <div className="field">
          <label htmlFor="founder-house-words">words</label>
          <input
            id="founder-house-words"
            type="text"
            value={draft.words}
            onChange={(event) => set('words', event.target.value)}
          />
        </div>
        <div className="field">
          <label htmlFor="founder-house-colors">colors</label>
          <input
            id="founder-house-colors"
            type="text"
            value={draft.colors}
            onChange={(event) => set('colors', event.target.value)}
          />
        </div>
      </div>
      <div className="field">
        <label htmlFor="founder-house-sigil">sigil</label>
        <textarea
          id="founder-house-sigil"
          className="prose"
          value={draft.sigil_description}
          onChange={(event) => set('sigil_description', event.target.value)}
        />
      </div>
      <div className="field">
        <label htmlFor="founder-house-backstory">the house</label>
        <textarea
          id="founder-house-backstory"
          className="prose"
          value={draft.backstory}
          onChange={(event) => set('backstory', event.target.value)}
        />
      </div>
      {quiddity && (
        <div className="field">
          <span className="label">House Quiddity</span>
          <p className="sub">{quiddity.prompt}</p>
          <ul className="entries">
            {quiddity.options.map((option) => {
              const picked = quiddityPicks.includes(option.id);
              return (
                <li key={option.id} className={picked ? 'on' : undefined}>
                  <span className="mark">{picked ? '◆' : ''}</span>
                  <span>
                    <button
                      type="button"
                      aria-pressed={picked}
                      onClick={() => toggleQuiddityOption(option.id, quiddity.max_picks ?? 1)}
                    >
                      <span className="nm">{option.name}</span>
                      {option.description && <span className="ds">{option.description}</span>}
                    </button>
                  </span>
                  <span className="rt">
                    {option.codex_entry_id != null && (
                      <a href={`/codex/${option.codex_entry_id}`}>codex</a>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}
      <div className="field">
        <span className="label">principles</span>
        {AXES.map((axis) => {
          const min = (template[axis.minKey] as number | undefined) ?? -5;
          const max = (template[axis.maxKey] as number | undefined) ?? 5;
          const raw = draft.principles[axis.key] ?? 0;
          const value = Math.min(max, Math.max(min, raw));
          return (
            <div className="range" key={axis.key}>
              <span>{axis.left}</span>
              <div className="track">
                <div
                  className="win"
                  style={{
                    left: `${((min + 5) / 10) * 100}%`,
                    width: `${((max - min) / 10) * 100}%`,
                  }}
                />
                <input
                  type="range"
                  min={min}
                  max={max}
                  value={value}
                  aria-label={`${axis.left} to ${axis.right}`}
                  onChange={(event) =>
                    set('principles', {
                      ...draft.principles,
                      [axis.key]: Number(event.target.value),
                    })
                  }
                />
              </div>
              <span>{axis.right}</span>
            </div>
          );
        })}
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
