import { describe, expect, it } from 'vitest';
import { examinePreview } from '../commissionCredits';

const base = {
  makerName: 'Corwen',
  designerName: null,
  myName: 'Linnet',
  writesText: false,
  madeForName: 'Linnet',
  facetWorkers: [],
  artistName: 'Corwen',
};

describe('examinePreview', () => {
  it('credits the commissioner as designer only when they write text', () => {
    expect(examinePreview({ ...base, writesText: true })).toBe(
      'Made by Corwen for Linnet. Designed by Linnet. Facet work by Corwen.'
    );
    expect(examinePreview(base)).toBe('Made by Corwen for Linnet. Facet work by Corwen.');
  });

  it('keeps the current designer when the commissioner writes nothing', () => {
    expect(examinePreview({ ...base, designerName: 'Ottilie' })).toBe(
      'Made by Corwen for Linnet. Designed by Ottilie. Facet work by Corwen.'
    );
  });

  it('collapses a maker who also designed, and lists earlier facet work once', () => {
    expect(
      examinePreview({
        ...base,
        designerName: 'Corwen',
        madeForName: null,
        facetWorkers: ['Brisa'],
        artistName: 'Corwen',
      })
    ).toBe('Made and designed by Corwen. Facet work by Brisa and Corwen.');
  });
});
