/**
 * The Reading Room's writing surfaces (#3941).
 *
 * A field here is a line to write on, not a box: a label in small caps above,
 * a hairline rule below, and nothing else. The composer, the respond form, the
 * inline editor and the block reason all use the same three, so the page never
 * has two different ideas of what writing looks like.
 */

export const FIELD_LABEL_CLASS =
  'jr-sans jr-soft text-[.75rem] uppercase tracking-[.1em] text-muted-foreground';

export const FIELD_INPUT_CLASS =
  'w-full rounded-none border-0 border-b bg-transparent px-0 py-[.35rem] font-body ' +
  'text-foreground focus:border-b-primary focus:outline-none';

export const PRIMARY_BUTTON_CLASS =
  'jr-sans cursor-pointer rounded-[2px] border border-primary bg-primary px-4 py-[.45rem] ' +
  'text-[.875rem] text-primary-foreground disabled:opacity-50';

export const QUIET_BUTTON_CLASS =
  'jr-sans cursor-pointer rounded-[2px] border bg-transparent px-4 py-[.45rem] text-[.875rem] ' +
  'text-foreground disabled:opacity-50';
