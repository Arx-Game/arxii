/**
 * A term that shows its definition (#4874, #5148, #5206): a card's effect ("+10 sailing",
 * the term underlined) or a row of the sheet's Bonuses band ("martial"), as a button, with
 * the term's definition in a drawn box.
 *
 * The box shows while the pointer or the keyboard focus is on the word; a click or tap
 * pins it open, for a screen with no pointer; Escape, a scroll or any other click closes
 * it. One box is open at a time per owner of `useTermPopover`.
 *
 * The box goes through a portal to `<body>` (a size container would otherwise anchor a
 * fixed box to itself), so it is outside the page's style root. It carries that root's
 * class itself (`interview` in character creation, `refsheet` on the sheet) and each
 * stylesheet styles it with a rule naming both classes on the one element
 * (`.interview.popover`, `.refsheet.popover`); `character-creation/__tests__/
 * portaledStyles.test.ts` holds that for both.
 */

import type { ReactNode } from 'react';
import { createPortal } from 'react-dom';

import type { OpenTerm, TermPopoverState } from './useTermPopover';

/**
 * The button that opens a term's box. Nothing that holds one may itself be a button: a
 * creation card is a plain box picked by the button on its name (`ChapterOffers`'s
 * `PickName`), so its effects stand beside that button, never inside it. A button is laid
 * out as one piece and does not wrap in the middle as text does, so a caller puts in it
 * everything that must stay with the term (a card's effect holds its number).
 */
export function TermButton({
  name,
  className,
  ariaLabel,
  popover,
  children,
}: {
  /** The term's key, the name the popover is opened under. */
  name: string;
  className: string;
  /** A name other than the button's own text; omit it where that text is read as part
   * of something else's description. */
  ariaLabel?: string;
  popover: TermPopoverState;
  children: ReactNode;
}) {
  const { peek, leave, pin } = popover;
  return (
    <button
      type="button"
      className={className}
      aria-label={ariaLabel}
      onMouseEnter={(e) => peek(e.currentTarget, name)}
      // Scrolling closes the box, and a pointer that was already on the word gets no
      // second enter: the next movement over the word shows it again.
      onMouseMove={(e) => peek(e.currentTarget, name)}
      onMouseLeave={() => leave(name)}
      onFocus={(e) => peek(e.currentTarget, name)}
      onBlur={() => leave(name)}
      onClick={(e) => {
        // The box closes on any click that reaches the document; this one opens it.
        e.stopPropagation();
        pin(e.currentTarget, name);
      }}
    >
      {children}
    </button>
  );
}

/** The drawn definition box for the open term, through a portal to `<body>`. */
export function TermPopover({
  openTerm,
  label,
  definition,
  scope,
}: {
  openTerm: OpenTerm | null;
  label: string;
  definition: string;
  /** The page's style root the box carries: character creation's or the sheet's. */
  scope: 'interview' | 'refsheet';
}) {
  if (!openTerm) return null;
  const style = { top: openTerm.top, left: openTerm.left };
  const body = (
    <>
      <b>{label}</b>
      {definition}
    </>
  );
  // Two literal class names, so the portaled-styles guard can read each one.
  return createPortal(
    scope === 'refsheet' ? (
      <dialog open className="refsheet popover" aria-label={label} style={style}>
        {body}
      </dialog>
    ) : (
      <dialog open className="interview popover" aria-label={label} style={style}>
        {body}
      </dialog>
    ),
    document.body
  );
}
