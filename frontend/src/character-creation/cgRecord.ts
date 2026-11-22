/**
 * The one "CG selections" record every stage shows (#5199).
 *
 * The owner's ruling of 2026-11-16 (#5148) is that every stage shows the same record,
 * with a stage's own choices under it. Until #5199 each stage wrote its own rows, so the
 * record changed shape from stage to stage: Path dropped Gender and the points, Attributes
 * added Family and dropped both, Appearance kept only Origin and Species. A stage now
 * takes `head` and `points` from here and puts its own rows between them:
 *
 *   rows={[...record.head, ...stageRows, record.points]}
 *
 * `head` is Name, Origin, Beginning, Species, Gender, Family, Path, Tradition. The Name
 * row is absent until a first name exists (#3630), and carries the surname once there is
 * one. On a route with no family the Family row is "Surname" and holds the surname the
 * tarot card gave, so it no longer reads "not yet chosen" after the card is drawn. The
 * surname is the server's (`draft.surname`), the same on every stage.
 *
 * The points row is marked `points`, and `RecordRail` gives a row so marked the page's
 * hover text: what becomes of points left unspent (#5201, `folio/pointsHint.ts`).
 */
import type { RecordRow } from './folio/RecordRail';
import { resolveFamilyPath, type CharacterDraft } from './types';
import { composeFullName } from './utils';

export interface CgRecord {
  head: RecordRow[];
  points: RecordRow;
}

interface CgRecordOverrides {
  /** A tradition line with more to say than the name (the Gift stage's schooling). */
  tradition?: string;
  /** Points as the page shows them while a pick is saving (`useShownPicks`). */
  points?: { spent: number; remaining: number };
}

export function cgRecord(draft: CharacterDraft, overrides: CgRecordOverrides = {}): CgRecord {
  const data = draft.draft_data;
  const path = resolveFamilyPath(draft);
  const surname = draft.surname ?? '';

  const firstName = data.first_name ?? '';
  const name = composeFullName(firstName, surname, '');
  const points = overrides.points ?? {
    spent: draft.cg_points_spent,
    remaining: draft.cg_points_remaining,
  };

  return {
    head: [
      ...(name ? [{ label: 'Name', value: name }] : []),
      { label: 'Origin', value: draft.selected_area?.name },
      { label: 'Beginning', value: draft.selected_beginnings?.name },
      { label: 'Species', value: draft.selected_species?.name },
      { label: 'Gender', value: draft.selected_gender?.display_name },
      path === 'none'
        ? { label: 'Surname', value: surname || undefined }
        : { label: 'Family', value: surname || undefined },
      { label: 'Path', value: draft.selected_path?.name },
      { label: 'Tradition', value: overrides.tradition ?? draft.selected_tradition?.name },
    ],
    points: {
      label: 'CG points',
      value: `${points.spent} of ${points.spent + points.remaining} spent`,
      points: true,
    },
  };
}
