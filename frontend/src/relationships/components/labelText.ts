/**
 * How a relationship label prints (#3957).
 *
 * One rule, stated once, because four surfaces draw the same chip: the cast on the
 * sheet, the plate on the tie page, the labels block under it, and the picker's
 * pending pill. Public awareness is UNMARKED by ruling — a marker is something the
 * reader has to be told, and "everyone may know this" is the resting state — so the
 * separator only ever appears where there is a marker to put after it.
 *
 * `former` wins over awareness: a label that has ended is no longer a secret being
 * kept, it is a thing that happened, and that is the only fact worth printing.
 */

/** The subset of a label any of the four surfaces has in hand. */
export interface LabelLike {
  type_name: string;
  awareness: string;
  is_former: boolean;
  is_mutual: boolean;
}

/** The chip's text: bare for public, and the marker only where there is one. */
export function labelText(label: LabelLike): string {
  if (label.is_former) return `${label.type_name} · former`;
  if (label.awareness === 'clandestine') return `${label.type_name} · Clandestine`;
  if (label.awareness === 'private') return `${label.type_name} · Private`;
  return label.type_name;
}

/**
 * The chip's classes. Awareness sets the border (dotted for ended, dashed for a label
 * not everyone may know); the type's `valence` colours it warm or hostile. Both the
 * tie payload and the sheet's own tie cards carry `valence`, so every surface that
 * draws a chip passes it — a chip's colour must not depend on which caller happened to
 * know it (#3957 demo-fidelity review, Finding 3).
 */
export function labelTagClass(label: LabelLike, valence?: string | null): string {
  const parts = ['refsheet-tag'];
  if (label.is_former) parts.push('refsheet-tag-former');
  else if (label.awareness === 'private') parts.push('refsheet-tag-private');
  else if (label.awareness === 'clandestine') parts.push('refsheet-tag-clandestine');
  if (valence === 'warm') parts.push('refsheet-tag-warm');
  if (valence === 'hostile') parts.push('refsheet-tag-hostile');
  return parts.join(' ');
}

/** ` · mutual` where the other side holds the counterpart, and nothing otherwise. */
export function mutualSuffix(label: LabelLike): string {
  return label.is_mutual && !label.is_former ? ' · mutual' : '';
}
