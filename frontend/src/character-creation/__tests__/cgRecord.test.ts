/**
 * The one "CG selections" record every stage shows (#5199).
 */
import { cgRecord } from '../cgRecord';
import type { CharacterDraft, OriginTemplate } from '../types';
import { mockEmptyDraft } from './fixtures';

const labels = (draft: CharacterDraft) => cgRecord(draft).head.map((row) => row.label);
const value = (draft: CharacterDraft, label: string) =>
  cgRecord(draft).head.find((row) => row.label === label)?.value;

const route = (paths: Partial<OriginTemplate>): OriginTemplate =>
  ({
    id: 1,
    name: 'A route',
    allows_claim_family: false,
    allows_name_family: false,
    allows_no_family: false,
    ...paths,
  }) as OriginTemplate;

describe('cgRecord', () => {
  it('has the same rows whatever has been chosen', () => {
    expect(labels(mockEmptyDraft)).toEqual([
      'Origin',
      'Beginning',
      'Species',
      'Gender',
      'Family',
      'Path',
      'Tradition',
    ]);
  });

  it('leaves the Name row out until a first name exists (#3630), then heads the record with it', () => {
    expect(labels(mockEmptyDraft)).not.toContain('Name');
    const named = { ...mockEmptyDraft, draft_data: { first_name: 'Marisol' } };
    expect(labels(named)[0]).toBe('Name');
    expect(value(named, 'Name')).toBe('Marisol');
  });

  it('writes the surname after the first name once the server has one', () => {
    const draft = { ...mockEmptyDraft, draft_data: { first_name: 'Marisol' }, surname: 'Thrax' };
    expect(value(draft, 'Name')).toBe('Marisol Thrax');
    expect(value(draft, 'Family')).toBe('Thrax');
  });

  it('calls the row "Surname" on a route with no family, and fills it from the drawn card', () => {
    const noFamily = {
      ...mockEmptyDraft,
      selected_origin_template: route({ allows_no_family: true }),
    };
    expect(labels(noFamily)).toContain('Surname');
    expect(labels(noFamily)).not.toContain('Family');
    expect(value(noFamily, 'Surname')).toBeUndefined();
    expect(value({ ...noFamily, surname: 'Downsword' }, 'Surname')).toBe('Downsword');
  });

  it('counts the points as spent of spent plus remaining, or as the stage shows them', () => {
    const draft = { ...mockEmptyDraft, cg_points_spent: 20, cg_points_remaining: 80 };
    expect(cgRecord(draft).points).toEqual({
      label: 'CG points',
      value: '20 of 100 spent',
      // The row the page's hover text about unspent points goes on (#5201).
      points: true,
    });
    expect(cgRecord(draft, { points: { spent: 35, remaining: 65 } }).points.value).toBe(
      '35 of 100 spent'
    );
  });

  it("takes the Gift stage's fuller tradition line", () => {
    expect(value(mockEmptyDraft, 'Tradition')).toBeUndefined();
    const row = cgRecord(mockEmptyDraft, { tradition: 'The Vigil · Sworn' }).head.find(
      (r) => r.label === 'Tradition'
    );
    expect(row?.value).toBe('The Vigil · Sworn');
  });
});
