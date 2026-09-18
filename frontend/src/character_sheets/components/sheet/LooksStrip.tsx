/**
 * The looks strip (#3898) — the character's images, beside the plate they fill.
 *
 * An OC reference sheet always carries a row of expressions next to the main art, and
 * this is that row built from what the character already has: their tenure media, each
 * optionally tagged with the mood it shows.
 *
 * Two behaviours, by viewer:
 * - The owner clicks a look to WEAR it — the strip sets the roster entry's profile
 *   picture, so the choice persists and every other surface showing this character
 *   follows. An Add tile links to the galleries.
 * - Anyone else clicks a look to SEE it — the big frame swaps locally and nothing is
 *   written. Their view is a flip-through, not an edit.
 *
 * Render-or-vanish: a character with no images renders no strip at all, and the plate
 * shows its empty frame instead.
 */

import { Link } from 'react-router-dom';
import type { CharacterSheetLook } from '@/character_sheets/api';

interface LooksStripProps {
  looks: CharacterSheetLook[];
  /** The look currently shown in the plate — the worn one, or one the viewer clicked. */
  shownId: number | null;
  onShow: (look: CharacterSheetLook) => void;
  /** True only on the owner's own sheet: clicking wears the look and the Add tile shows. */
  canWear: boolean;
  /**
   * Where the "All galleries" link sends this reader, or null for no link.
   *
   * It differs by viewer, and getting it wrong is easy: the owner's galleries live in
   * the player area (`/profile/media`), because media hangs off the tenure and follows
   * the player rather than the character. A visitor must never be sent there — that
   * page is their own media — so they get the character's own public gallery link, or
   * nothing when the character has published none.
   */
  galleriesTo: string | null;
  /** True while a wear request is in flight, so the strip does not invite a second one. */
  isSaving: boolean;
}

export function LooksStrip({
  looks,
  shownId,
  onShow,
  canWear,
  galleriesTo,
  isSaving,
}: LooksStripProps) {
  if (looks.length === 0) return null;

  return (
    <div className="flex flex-col gap-2">
      <div className="flex items-baseline justify-between gap-3">
        <span className="refsheet-eyebrow" style={{ fontSize: '0.6875rem' }}>
          Looks and expressions
        </span>
        {galleriesTo && (
          <Link to={galleriesTo} className="text-sm">
            All galleries
          </Link>
        )}
      </div>
      <div className="refsheet-looks" role="group" aria-label="Looks and expressions">
        {looks.map((look) => {
          // The label is the mood when one is tagged, else the image's own title, else
          // nothing — an untagged image still belongs in the strip.
          const label = look.look || look.title;
          return (
            <button
              key={look.tenure_media_id}
              type="button"
              className="refsheet-look"
              aria-pressed={look.tenure_media_id === shownId}
              disabled={isSaving}
              onClick={() => onShow(look)}
              title={canWear ? `Wear ${label || 'this look'}` : label || undefined}
            >
              <img src={look.url} alt="" />
              {label && <span>{label}</span>}
            </button>
          );
        })}
        {canWear && galleriesTo && (
          <Link
            to={galleriesTo}
            className="refsheet-look refsheet-look-add"
            aria-label="Add a look from your galleries"
          >
            <span>Add</span>
          </Link>
        )}
      </div>
    </div>
  );
}
