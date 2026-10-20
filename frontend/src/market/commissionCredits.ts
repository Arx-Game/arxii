/**
 * The credits a piece will carry once a commission lands (#4512): "Made by X for Y.
 * Designed by Z. Facet work by W." This mirrors `crafted_provenance_line` on the server
 * (`world/items/services/crafted_display.py`), which is what examine really prints; the
 * form shows it before the commissioner pays so they can see what writing text does.
 */

export interface CommissionCreditInputs {
  /** The persona that signed the piece (`crafter_name`); null for an uncrafted item. */
  makerName: string | null;
  /** Who is credited as designer now (`designer_name`); null when nobody wrote its words. */
  designerName: string | null;
  /** The commissioner's persona, credited as designer only when they write text. */
  myName: string;
  /** Whether the commissioner wrote a name or a description. */
  writesText: boolean;
  /** Who the piece is already made for, or who the commissioner picked. */
  madeForName: string | null;
  /** Artists who already did facet or style work on it. */
  facetWorkers: string[];
  /** The artist being commissioned now. */
  artistName: string;
}

function joinProse(parts: string[]): string {
  if (parts.length <= 1) return parts[0] ?? '';
  return `${parts.slice(0, -1).join(', ')} and ${parts[parts.length - 1]}`;
}

export function examinePreview(inputs: CommissionCreditInputs): string {
  const designer = inputs.writesText ? inputs.myName : inputs.designerName;
  const forClause = inputs.madeForName ? ` for ${inputs.madeForName}` : '';
  const sentences: string[] = [];
  if (inputs.makerName && designer && inputs.makerName === designer) {
    sentences.push(`Made and designed by ${inputs.makerName}${forClause}.`);
  } else {
    if (inputs.makerName) sentences.push(`Made by ${inputs.makerName}${forClause}.`);
    else if (inputs.madeForName) sentences.push(`Made for ${inputs.madeForName}.`);
    if (designer) sentences.push(`Designed by ${designer}.`);
  }
  const workers = inputs.facetWorkers.includes(inputs.artistName)
    ? inputs.facetWorkers
    : [...inputs.facetWorkers, inputs.artistName];
  sentences.push(`Facet work by ${joinProse(workers)}.`);
  return sentences.join(' ');
}
