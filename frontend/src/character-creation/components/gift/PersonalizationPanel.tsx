/**
 * PersonalizationPanel (#4099): "Make it yours" for one chosen technique.
 *
 * Every sentence is a CGExplanation row (decision 9): no copy literals here. Picks
 * are stance rows (the CG price grammar, #3709): name, authored gloss, a mechanics
 * line, and the option's own CG-point cost. Pressing a pressed row clears it.
 *
 * Flourishes and forms are resonance-gated (the server only offers them once the
 * Gift Resonance step has run), so `options.needs_resonance` shows one wait line,
 * between the two sections, instead of either stance list.
 */
import { useState, type ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { Field } from '../../folio';
import { characterCreationKeys, useUpdateDraft } from '../../queries';
import type {
  CGExplanations,
  CharacterDraft,
  PersonalizationOption,
  TechniquePersonalizationOptions,
  TechniquePersonalizationPick,
} from '../../types';

type PickKey = 'signature_bonus_id' | 'early_form_id' | 'price_id';

function signed(n: number): string {
  return n >= 0 ? `+${n}` : String(n);
}

// Every Cc-category (control) code point, matching unicodedata's own category
// test in the server's `_has_control_character` (technique_personalization.py).
const CONTROL_CHAR = /\p{Cc}/gu;

/**
 * Client-side UX pre-check only (the server is the real validator —
 * `clean_custom_technique_name`, `technique_personalization.py`): an em dash
 * (U+2014) or en dash (U+2013) is not on anyone's keyboard, so a player who
 * pastes one almost certainly meant a hyphen; `|` is Evennia markup in
 * telnet and never allowed in a name; a control character (including a
 * newline — a name is single-line) is stripped outright. Length is capped
 * separately by the input's own `maxLength`.
 */
export function sanitizeCustomName(value: string): string {
  return value.replace(/[–—]/g, '-').replace(/\|/g, '').replace(CONTROL_CHAR, '');
}

/**
 * Client-side UX pre-check for a description — mirrors
 * `clean_custom_technique_description`: control characters are stripped,
 * except a newline (paragraph breaks are allowed in a description). No dash
 * rule here: the dash rule is name-only, both server-side and here.
 */
export function sanitizeCustomDescription(value: string): string {
  return value.replace(CONTROL_CHAR, (ch) => (ch === '\n' ? ch : ''));
}

/** "1 pt" / "4 pts" (the demo's cost chip, never a bare number). */
function formatCost(cost: number): string {
  return cost === 1 ? '1 pt' : `${cost} pts`;
}

/** "+1 intensity · +4 power" — mechanics only, never prose, never the level. */
function mechanicsLine(option: PersonalizationOption): string {
  const parts: string[] = [];
  if (option.intensity_delta) parts.push(`${signed(option.intensity_delta)} intensity`);
  if (option.control_delta) parts.push(`${signed(option.control_delta)} control`);
  if (option.power_bonus) parts.push(`+${option.power_bonus} power`);
  return parts.join(' · ');
}

interface Props {
  draft: CharacterDraft;
  options: TechniquePersonalizationOptions;
  copy?: CGExplanations;
}

export function PersonalizationPanel({ draft, options, copy }: Props) {
  const updateDraft = useUpdateDraft();
  const queryClient = useQueryClient();
  const key = String(options.technique_id);
  const all = draft.draft_data.technique_personalizations ?? {};
  const pick: TechniquePersonalizationPick = all[key] ?? {};
  const [name, setName] = useState(pick.custom_name ?? '');
  const [description, setDescription] = useState(pick.custom_description ?? '');

  // The freshest known picks, read from the query cache rather than this
  // render's `draft` prop: two panels (different techniques) can each mutate
  // off a render that predates the other's pick, and a cache write from the
  // first survives in the cache before this component ever re-renders with
  // it. Reading the cache at mutation time, not render time, is what the
  // existing `useUpdateDraft` optimistic merge (queries.ts) already relies on.
  const latestPersonalizations = (): Record<string, TechniquePersonalizationPick> => {
    const cached = queryClient.getQueryData<CharacterDraft>(characterCreationKeys.draft());
    return (cached ?? draft).draft_data.technique_personalizations ?? {};
  };

  const write = (
    apply: (currentPick: TechniquePersonalizationPick) => TechniquePersonalizationPick
  ) => {
    const latestAll = latestPersonalizations();
    const currentPick = latestAll[key] ?? {};
    updateDraft.mutate({
      draftId: draft.id,
      data: {
        draft_data: {
          technique_personalizations: { ...latestAll, [key]: apply(currentPick) },
        },
      },
    });
  };

  const toggle = (field: PickKey, id: number) =>
    write((currentPick) => ({ ...currentPick, [field]: currentPick[field] === id ? null : id }));

  const stanceList = (field: PickKey, rows: PersonalizationOption[]) => (
    <ul className="stances">
      {rows.map((row) => (
        <li key={row.id}>
          <button
            type="button"
            className="stance"
            aria-pressed={pick[field] === row.id}
            onClick={() => toggle(field, row.id)}
          >
            <span className="dot" />
            <span>
              <b>{row.name}</b>
              {row.gloss && <span className="g">{row.gloss}</span>}
              {mechanicsLine(row) && <span className="fx">{mechanicsLine(row)}</span>}
            </span>
            <span className="price">
              <span className="cost">{formatCost(row.cost)}</span>
            </span>
          </button>
        </li>
      ))}
    </ul>
  );

  const section = (titleKey: string, glossKey: string, body: ReactNode) => (
    <div>
      {copy?.[titleKey] && <span className="panel-label">{copy[titleKey]}</span>}
      {copy?.[glossKey] && <p className="ledger-line">{copy[glossKey]}</p>}
      {body}
    </div>
  );

  const waitLine = options.needs_resonance && copy?.personalize_needs_resonance && (
    <p className="ledger-line">{copy.personalize_needs_resonance}</p>
  );

  return (
    <section aria-label={copy?.personalize_heading}>
      {copy?.personalize_heading && <h4 className="section-h">{copy.personalize_heading}</h4>}
      {section(
        'personalize_name_title',
        'personalize_name_gloss',
        <>
          <Field id={`pz-name-${key}`} label={copy?.personalize_name_label ?? ''}>
            <input
              id={`pz-name-${key}`}
              type="text"
              maxLength={80}
              value={name}
              onChange={(e) => setName(sanitizeCustomName(e.target.value))}
              onBlur={() =>
                name !== (pick.custom_name ?? '') &&
                write((currentPick) => ({ ...currentPick, custom_name: name }))
              }
            />
          </Field>
          <Field
            id={`pz-desc-${key}`}
            label={copy?.personalize_description_label ?? ''}
            hint={copy?.personalize_free_note}
          >
            <textarea
              id={`pz-desc-${key}`}
              rows={3}
              maxLength={2000}
              value={description}
              onChange={(e) => setDescription(sanitizeCustomDescription(e.target.value))}
              onBlur={() =>
                description !== (pick.custom_description ?? '') &&
                write((currentPick) => ({ ...currentPick, custom_description: description }))
              }
            />
          </Field>
          {copy?.personalize_mechanics_note && (
            <p className="mech-note">{copy.personalize_mechanics_note}</p>
          )}
        </>
      )}
      {section(
        'personalize_flourish_title',
        'personalize_flourish_gloss',
        options.needs_resonance ? null : stanceList('signature_bonus_id', options.flourishes)
      )}
      {waitLine}
      {section(
        'personalize_form_title',
        'personalize_form_gloss',
        options.needs_resonance ? null : stanceList('early_form_id', options.forms)
      )}
      {section(
        'personalize_price_title',
        'personalize_price_gloss',
        stanceList('price_id', options.prices)
      )}
      {updateDraft.isError && (
        <p className="hint">{copy?.offers_sync_error ?? 'That pick did not save. Try again.'}</p>
      )}
    </section>
  );
}
