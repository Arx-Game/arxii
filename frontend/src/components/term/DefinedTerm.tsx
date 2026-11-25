/**
 * A term that shows its definition (#4874, #5148, #5206): the word a card or the sheet's
 * Bonuses band prints ("+10 sailing", "martial"), underlined, with its definition in a
 * drawn box.
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
 * The underlined word. A span with the button role: a card around it may already be a
 * button, and a button may not nest one.
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
  ariaLabel: string;
  popover: TermPopoverState;
  children: ReactNode;
}) {
  const { peek, leave, pin } = popover;
  return (
    <span
      role="button"
      tabIndex={0}
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
        e.stopPropagation();
        pin(e.currentTarget, name);
      }}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault();
          e.stopPropagation();
          pin(e.currentTarget, name);
        }
      }}
    >
      {children}
    </span>
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
