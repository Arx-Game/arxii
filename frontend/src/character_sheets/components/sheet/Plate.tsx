/**
 * The plate (#3898) — the head of the character sheet.
 *
 * Art on the left, and on the right the character in their own terms: the name with any
 * titles composed into the same heading, their concept, their quote, two short lines at
 * a glance, and the looks strip. Nothing mechanical appears here — no health, no
 * fatigue, no attributes. Those are read on Physical, where a reader goes looking for
 * them.
 *
 * The plate is painted in explicit night literals in both themes (the ink tokens in
 * `sheet.css`): it is the cover of the page, and a cover is the same object whichever
 * way the reader has the lights.
 */

import { useState } from 'react';
import type { ReactNode } from 'react';
import { Link } from 'react-router-dom';
import type { CharacterSheetLook } from '@/character_sheets/api';
import { LooksStrip } from './LooksStrip';

interface PlateProps {
  /** The presented name — the real one only when the viewer may see it. */
  name: string;
  /** Titles this face has earned, already ordered; rendered as one composed line. */
  titles: string[];
  concept: string;
  quote: string;
  /** Two short lines: who they are, then what they look like. Blank ones vanish. */
  glanceLines: string[];
  looks: CharacterSheetLook[];
  canWear: boolean;
  onWear: (look: CharacterSheetLook) => void;
  isSaving: boolean;
  /** Where 'All galleries' points for THIS viewer; null for no link. */
  galleriesTo: string | null;
  /** Owner-only doors (friend/rival buttons live here on a foreign sheet). */
  actions?: ReactNode;
}

export function Plate({
  name,
  titles,
  concept,
  quote,
  glanceLines,
  looks,
  canWear,
  onWear,
  isSaving,
  galleriesTo,
  actions,
}: PlateProps) {
  // Which look the frame is showing. Null means "whatever is worn", which is the entry
  // the server marked current. A viewer clicking the strip moves this locally; the
  // owner clicking it also writes, and the refetched payload moves `is_current` to match.
  const [previewId, setPreviewId] = useState<number | null>(null);
  const worn = looks.find((look) => look.is_current) ?? looks[0] ?? null;
  const shown = (previewId !== null && looks.find((l) => l.tenure_media_id === previewId)) || worn;

  // What the empty frame is waiting on: the clicked look, else the worn one.
  const shownLookName = shown?.look || shown?.title || '';

  const handleShow = (look: CharacterSheetLook) => {
    setPreviewId(look.tenure_media_id);
    if (canWear) onWear(look);
  };

  return (
    <div className="refsheet-plate">
      <div className="flex flex-col gap-2">
        <div className="refsheet-frame">
          {shown ? (
            <img src={shown.url} alt={`${name}${shown.look ? `, ${shown.look}` : ''}`} />
          ) : (
            <>
              <span className="refsheet-frame-empty" aria-hidden="true">
                <PortraitGlyph />
              </span>
              {canWear && (
                <>
                  <span className="refsheet-frame-note refsheet-plate-soft text-sm">
                    {/* Naming the look says WHICH image is missing, so the sentence
                        changes as the strip is clicked rather than reading as a single
                        permanent state. */}
                    {shownLookName ? `No art yet for ${shownLookName}. ` : 'No art yet. '}
                    The frame waits.
                  </span>
                  {galleriesTo && (
                    <Link to={galleriesTo} className="refsheet-frame-note text-sm">
                      Choose from your galleries
                    </Link>
                  )}
                </>
              )}
            </>
          )}
        </div>
        {/* The caption says only what the page actually does. An earlier draft promised
            "a scene can change it with their mood", which nothing delivers: the worn
            look is whichever image the owner last clicked, and the character's declared
            mood is inward and owner-only (#2994), so driving a public portrait from it
            would publish the one thing that ruling keeps private. Whether a look should
            follow a mood at all is an open question, recorded in the roadmap. */}
        {canWear && looks.length > 0 && (
          <p className="refsheet-plate-soft text-sm">
            {shown?.is_current
              ? `Wearing ${shown.look || shown.title || 'this look'}.`
              : 'Click a look to wear it.'}
          </p>
        )}
      </div>

      <div className="refsheet-plate-body">
        <h1 className="refsheet-name">
          {name}
          {titles.length > 0 && <span className="refsheet-title">{titles.join(' · ')}</span>}
        </h1>
        {concept && <p className="refsheet-concept">{concept}</p>}
        {quote && <blockquote className="refsheet-quote">{quote}</blockquote>}

        {glanceLines.filter(Boolean).length > 0 && (
          <>
            <hr />
            <div className="flex flex-col gap-1">
              {glanceLines.filter(Boolean).map((line) => (
                <p key={line} className="refsheet-plate-soft text-base">
                  {line}
                </p>
              ))}
            </div>
          </>
        )}

        {looks.length > 0 && (
          <div className="refsheet-plate-foot flex flex-col gap-3">
            <hr />
            <LooksStrip
              looks={looks}
              shownId={shown?.tenure_media_id ?? null}
              onShow={handleShow}
              canWear={canWear}
              galleriesTo={galleriesTo}
              isSaving={isSaving}
            />
          </div>
        )}

        {actions && <div className="flex flex-wrap gap-4 pt-1">{actions}</div>}
      </div>
    </div>
  );
}

/** The empty frame's mark. Decorative only — the copy beside it carries the meaning. */
function PortraitGlyph() {
  return (
    <svg
      width="72"
      height="72"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <rect x="3" y="3" width="18" height="18" />
      <circle cx="12" cy="10" r="3" />
      <path d="M6 20c1.5-3.5 4-5 6-5s4.5 1.5 6 5" />
    </svg>
  );
}
