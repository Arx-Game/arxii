/**
 * The picks of one Glimpse axis after a click on one of its tags.
 *
 * One place for the rule, read by both mounts (`GlimpseAxes` in character
 * creation and the shared `GlimpseFlow` on the sheet), so the two cannot
 * drift:
 *
 * - a click on a picked tag lets it go;
 * - an axis that takes one answer swaps to the clicked tag;
 * - an axis that takes several adds the clicked tag, except that a tag
 *   which stands alone (`stands_alone`, #5193: an answer that rules the
 *   rest out, such as Fugue in The Reflection) replaces every other pick,
 *   and picking any other tag lets a stand-alone one go.
 *
 * The server holds the same rule (`set_glimpse_tags`), so a list this
 * returns is one it accepts.
 */

import type { GlimpseTagOption } from './glimpseTypes';

export function nextAxisSelection(
  axisTags: GlimpseTagOption[],
  selectedTagIds: number[],
  clickedTagId: number,
  multi: boolean
): number[] {
  const axisTagIds = new Set(axisTags.map((tag) => tag.id));
  const current = selectedTagIds.filter((id) => axisTagIds.has(id));
  if (current.includes(clickedTagId)) {
    return current.filter((id) => id !== clickedTagId);
  }
  if (!multi) {
    return [clickedTagId];
  }
  const standAloneIds = new Set(axisTags.filter((tag) => tag.stands_alone).map((tag) => tag.id));
  if (standAloneIds.has(clickedTagId)) {
    return [clickedTagId];
  }
  return [...current.filter((id) => !standAloneIds.has(id)), clickedTagId];
}
