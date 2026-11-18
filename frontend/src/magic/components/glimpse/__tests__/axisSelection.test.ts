import { nextAxisSelection } from '../axisSelection';
import type { GlimpseTagOption } from '../glimpseTypes';

function tag(id: number, name: string, standsAlone = false): GlimpseTagOption {
  return {
    id,
    axis: 'REFLECTION',
    name,
    slug: name.toLowerCase(),
    description: '',
    example: '',
    sort_order: id,
    stands_alone: standsAlone,
    offers: [],
  };
}

const MAJESTIC = tag(1, 'Majestic');
const TERRIFYING = tag(2, 'Terrifying');
const FUGUE = tag(3, 'Fugue', true);
const REFLECTION = [MAJESTIC, TERRIFYING, FUGUE];
// A pick on another axis, which no click on this one may touch or return.
const OTHER_AXIS_PICK = 99;

describe('nextAxisSelection', () => {
  it('adds a tag on an axis that takes several', () => {
    expect(nextAxisSelection(REFLECTION, [1, OTHER_AXIS_PICK], 2, true)).toEqual([1, 2]);
  });

  it('lets a picked tag go on a second click', () => {
    expect(nextAxisSelection(REFLECTION, [1, 2], 1, true)).toEqual([2]);
  });

  it('swaps to the clicked tag on an axis that takes one', () => {
    expect(nextAxisSelection(REFLECTION, [1], 2, false)).toEqual([2]);
    expect(nextAxisSelection(REFLECTION, [2], 2, false)).toEqual([]);
  });

  it('a tag that stands alone replaces every other pick of its axis (#5193)', () => {
    expect(nextAxisSelection(REFLECTION, [1, 2, OTHER_AXIS_PICK], 3, true)).toEqual([3]);
  });

  it('picking another tag lets a stand-alone one go (#5193)', () => {
    expect(nextAxisSelection(REFLECTION, [3], 1, true)).toEqual([1]);
  });

  it('a second click on a stand-alone tag clears the axis (#5193)', () => {
    expect(nextAxisSelection(REFLECTION, [3], 3, true)).toEqual([]);
  });
});
