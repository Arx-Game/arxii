import { act, renderHook } from '@testing-library/react';
import { vi } from 'vitest';

import type { HouseTemplateOption } from '@/character-creation/api';
import { toClaimPayload, useFounderDraft, type FounderDraft } from '../founder/founderDraft';

const template = { id: 3 } as HouseTemplateOption;

function baseDraft(): FounderDraft {
  return {
    realm_id: 1,
    title_id: 12,
    template_id: 3,
    house_name: 'Candela',
    words: 'The Debt Is Kept',
    colors: 'oxblood and slate',
    sigil_description: 'A coiled serpent in gold.',
    backstory: 'The house as it has always been.',
    aspect_picks: { 1: [5] },
    principles: { mercy: 1, method: -2, status: 0, change: 0, allegiance: 3, power: 0 },
    founder_relation: 'child',
    founder_is_heir: true,
    kin: [
      {
        key: 'k1',
        name: 'Estuosa',
        relation: 'head',
        gender_id: null,
        age: null,
        is_deceased: false,
        born_into_id: null,
        born_into_name: '',
        is_household: false,
      },
      {
        key: 'k2',
        name: 'Dario',
        relation: 'father',
        gender_id: 2,
        age: 44,
        is_deceased: false,
        born_into_id: 9,
        born_into_name: 'Solano',
        is_household: false,
      },
    ],
    lands: {
      12: {
        title_id: 12,
        land_name: '',
        description: 'Terraces above the bay.',
        hall_name: '',
        land_shape_names: ['Coast'],
      },
    },
    estate_name: 'Casa Candela',
    estate_description: 'A quiet townhouse above the harbor.',
  };
}

test('toClaimPayload maps kin, lands, and the estate to the nested claim shape exactly', () => {
  const payload = toClaimPayload(baseDraft(), template);

  expect(payload).toEqual({
    title: 12,
    template: 3,
    house_name: 'Candela',
    backstory: 'The house as it has always been.',
    words: 'The Debt Is Kept',
    colors: 'oxblood and slate',
    sigil_description: 'A coiled serpent in gold.',
    aspects: [{ definition: 1, options: [5] }],
    mercy: 1,
    method: -2,
    status: 0,
    change: 0,
    allegiance: 3,
    power: 0,
    founder_relation: 'child',
    founder_is_heir: true,
    kin: [
      {
        name: 'Estuosa',
        relation: 'head',
        gender: null,
        age: null,
        is_deceased: false,
        born_into: null,
        basis: '',
        is_household: false,
      },
      {
        name: 'Dario',
        relation: 'father',
        gender: 2,
        age: 44,
        is_deceased: false,
        born_into: 9,
        basis: '',
        is_household: false,
      },
    ],
    lands: [
      {
        title: 12,
        land_name: '',
        description: 'Terraces above the bay.',
        hall_name: '',
        land_shapes: ['Coast'],
      },
    ],
    estate: { name: 'Casa Candela', description: 'A quiet townhouse above the harbor.' },
  });
});

test('useFounderDraft starts empty and renders even when localStorage throws', () => {
  vi.spyOn(window.localStorage, 'getItem').mockImplementation(() => {
    throw new Error('storage blocked');
  });
  vi.spyOn(window.localStorage, 'setItem').mockImplementation(() => {
    throw new Error('storage blocked');
  });

  const { result } = renderHook(() => useFounderDraft(42));
  expect(result.current.draft.house_name).toBe('');
  expect(result.current.draft.kin).toEqual([]);

  act(() => {
    result.current.set('house_name', 'Candela');
  });
  expect(result.current.draft.house_name).toBe('Candela');

  act(() => {
    result.current.addKin({
      name: 'Estuosa',
      relation: 'head',
      gender_id: null,
      age: null,
      is_deceased: false,
      born_into_id: null,
      born_into_name: '',
      is_household: false,
    });
  });
  expect(result.current.draft.kin).toHaveLength(1);

  vi.restoreAllMocks();
});

describe('useFounderDraft composes writes made in one handler', () => {
  it('keeps every field when set is called three times back to back', () => {
    localStorage.clear();
    const { result } = renderHook(() => useFounderDraft(77));
    act(() => {
      result.current.set('title_id', 12);
      result.current.set('realm_id', 3);
      result.current.set('template_id', 950);
    });
    expect(result.current.draft.title_id).toBe(12);
    expect(result.current.draft.realm_id).toBe(3);
    expect(result.current.draft.template_id).toBe(950);
    const stored = JSON.parse(localStorage.getItem('almanach-founder-77') ?? '{}') as FounderDraft;
    expect(stored.title_id).toBe(12);
    expect(stored.realm_id).toBe(3);
    expect(stored.template_id).toBe(950);
  });
});
