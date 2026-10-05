/**
 * The looks strip (#3898, #4151) — the character's faces, beside the plate they fill.
 *
 * An artist's reference sheet carries a row of expressions next to the main art; this
 * is that row, built from the character's looks: pictures framed with a 4:5 crop, each
 * labelled with the mood it shows. Several looks can show the same mood, so a repeat is
 * numbered ("Furious", "Furious 2").
 *
 * Two behaviours, by viewer:
 * - The owner clicks a look to WEAR it, and the Add tile opens the Add a look flow.
 * - Anyone else clicks a look to SEE it: the big frame swaps locally, nothing is written.
 *
 * Render-or-vanish: with no looks, a visitor sees no strip at all; the owner sees only
 * the Add tile.
 */

import type { CharacterSheetLook } from '@/character_sheets/api';
import { lookLabels } from './gallery/labels';

interface LooksStripProps {
  looks: CharacterSheetLook[];
  /** The look currently shown in the plate — the worn one, or one the viewer clicked. */
  shownId: number | null;
  onShow: (look: CharacterSheetLook) => void;
  /** True only on the owner's own sheet: clicking wears the look. */
  canWear: boolean;
  /** Owner only: open the Add a look flow. */
  onAdd?: () => void;
  /** True while a wear request is in flight, so the strip does not invite a second one. */
  isSaving: boolean;
}

export function LooksStrip({ looks, shownId, onShow, canWear, onAdd, isSaving }: LooksStripProps) {
  if (looks.length === 0 && !onAdd) return null;
  const labels = lookLabels(looks);

  return (
    <div className="flex flex-col gap-2">
      <span className="refsheet-eyebrow" style={{ fontSize: '0.6875rem' }}>
        Looks and expressions
      </span>
      <div className="refsheet-looks" role="group" aria-label="Looks and expressions">
        {looks.map((look) => {
          const label = labels.get(look.tenure_media_id) ?? '';
          return (
            <button
              key={look.tenure_media_id}
              type="button"
              className="refsheet-look"
              aria-pressed={look.tenure_media_id === shownId}
              aria-label={label || look.title || 'Look'}
              disabled={isSaving}
              onClick={() => onShow(look)}
              title={canWear ? `Wear ${label || look.title || 'this look'}` : label || undefined}
            >
              <img src={look.url} alt="" />
              {label && <span>{label}</span>}
            </button>
          );
        })}
        {onAdd && (
          <button
            type="button"
            className="refsheet-look refsheet-look-add"
            aria-label="Add a look"
            onClick={onAdd}
          >
            <span>Add</span>
          </button>
        )}
      </div>
    </div>
  );
}
