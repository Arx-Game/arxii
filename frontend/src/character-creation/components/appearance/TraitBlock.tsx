/**
 * One physical feature on the Appearance stage (#5241): its picker, its qualities
 * line, and its description once it is distinctive.
 *
 * The picker depends on what the feature is. A colour (`trait_type` "color") is a
 * strip of swatches with the chosen colour's name beside the feature's name; any
 * other feature is one dropdown. Until #5241 both were a row of buttons, one per
 * option (27 for hair colour), and a page of such rows read as one block (owner
 * ruling 2026-11-21).
 *
 * `options` is what the feature offers now: the species' own list plus anything a
 * parent line passes down, or every option the trait carries once the feature is
 * distinctive. `ownIds` says which of those the ordinary list holds, so the rest
 * are drawn apart (a dashed swatch, a "Distinctive" group in the dropdown).
 */

import { useState } from 'react';
import { Field, SwatchRow } from '../../folio';
import { FeatureDistinctions } from '../offers/FeatureDistinctions';
import type { CharacterDraft, FormTrait, FormTraitOption } from '../../types';

interface TraitBlockProps {
  draft: CharacterDraft;
  trait: FormTrait;
  /** Makes the block's element ids unique when one trait appears twice on the page. */
  idSuffix?: string;
  options: FormTraitOption[];
  /** The ids of the options the feature offers without being distinctive. */
  ownIds: Set<number>;
  /** The feature holds a tier of some quality: every option and the description are open. */
  opened: boolean;
  required?: boolean;
  /** Where an inherited feature comes from, e.g. a parent's species. */
  source?: string;
  selectedId: number | null;
  onSelect: (optionId: number | null) => void;
  descriptor: string;
  onDescriptorCommit: (text: string) => void;
  /** The last tier came off this feature. */
  onClosed: () => void;
}

export function TraitBlock({
  draft,
  trait,
  idSuffix = '',
  options,
  ownIds,
  opened,
  required = false,
  source,
  selectedId,
  onSelect,
  descriptor,
  onDescriptorCommit,
  onClosed,
}: TraitBlockProps) {
  const [preview, setPreview] = useState<string | null>(null);
  const key = `${trait.id}${idSuffix}`;
  const isColour = trait.trait_type === 'color';
  const chosen = options.find((o) => o.id === selectedId) ?? null;
  const ordinary = options.filter((o) => ownIds.has(o.id));
  const beyond = options.filter((o) => !ownIds.has(o.id));
  const name = `${trait.display_name}${required ? ' (required)' : ''}`;
  const gloss = source ? <span className="entry-gloss"> (from {source})</span> : null;

  return (
    <div className={isColour ? 'trait trait-colour' : 'trait'}>
      {isColour ? (
        <>
          <h3 className="trait-h" id={`trait-${key}`}>
            {name}
            {gloss}
            <span className="trait-chosen">{preview ?? chosen?.display_name ?? ''}</span>
          </h3>
          <SwatchRow
            labelledBy={`trait-${key}`}
            options={options.map((o) => ({
              value: o.id,
              label: o.display_name,
              hex: o.swatch_hex,
              beyond: !ownIds.has(o.id),
            }))}
            value={selectedId}
            onChange={onSelect}
            clearable={!required}
            onPreview={setPreview}
          />
        </>
      ) : (
        <Field id={`trait-${key}`} label={source ? `${name} (from ${source})` : name}>
          <select
            id={`trait-${key}`}
            value={selectedId ?? ''}
            onChange={(e) => onSelect(e.target.value === '' ? null : Number(e.target.value))}
          >
            {/* A required feature cannot go back to nothing; any other can. */}
            {required ? (
              selectedId === null && (
                <option value="" disabled>
                  Select
                </option>
              )
            ) : (
              <option value="" aria-label="Not chosen" />
            )}
            {ordinary.map((o) => (
              <option key={o.id} value={o.id}>
                {o.display_name}
              </option>
            ))}
            {beyond.length > 0 && (
              <optgroup label="Distinctive">
                {beyond.map((o) => (
                  <option key={o.id} value={o.id}>
                    {o.display_name}
                  </option>
                ))}
              </optgroup>
            )}
          </select>
        </Field>
      )}
      <FeatureDistinctions
        draft={draft}
        feature={{ feature_trait: trait.name }}
        featureLabel={trait.display_name}
        onClosed={onClosed}
      />
      {opened && (
        <Field id={`desc-${key}`} label="Describe it" hint="Optional.">
          <input
            id={`desc-${key}`}
            type="text"
            maxLength={120}
            defaultValue={descriptor}
            onBlur={(e) => onDescriptorCommit(e.target.value)}
          />
        </Field>
      )}
    </div>
  );
}
