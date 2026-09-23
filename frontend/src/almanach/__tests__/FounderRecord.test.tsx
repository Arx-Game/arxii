/**
 * FounderRecord (#3983 Plan B Task 6, plate F-VI) — "the family" line quotes
 * every named kin styled with the charter particle (`taken_in` for a
 * spouse, `born` for everyone else) plus a trailing descriptor, the
 * founder's own placement inserted at her `founder_relation`'s slot, and a
 * nameless kin reading "a <relation>, to be defined". Submit posts the
 * nested `toClaimPayload` shape through `submitHouseClaim`.
 */
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import type { HouseClaimStatus, HouseTemplateOption } from '@/character-creation/api';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { FounderRecord } from '../founder/FounderRecord';
import type { FounderDraft } from '../founder/founderDraft';

vi.mock('@/character-creation/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/character-creation/api')>();
  return { ...actual, submitHouseClaim: vi.fn() };
});

vi.mock('../queries', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../queries')>();
  return {
    ...actual,
    useCharter: () => ({
      data: {
        succession_law: null,
        particle: { born: 'za', taken_in: 'zas' },
        quiddity_prompt: '',
        capital_name: 'Perdition',
      },
    }),
  };
});

import { submitHouseClaim } from '@/character-creation/api';

function draft(): FounderDraft {
  return {
    realm_id: 1,
    title_id: 1,
    template_id: 3,
    house_name: 'Candela',
    words: 'The Debt Is Kept',
    colors: 'oxblood and slate',
    sigil_description: 'A raven, wings spread.',
    backstory: 'An old house of the southern isle.',
    aspect_picks: {},
    principles: {},
    founder_relation: 'child',
    founder_is_heir: true,
    kin: [
      {
        key: 'head',
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
        key: 'spouse',
        name: 'Dario',
        relation: 'spouse',
        gender_id: null,
        age: null,
        is_deceased: false,
        born_into_id: 5,
        born_into_name: 'Solano',
        is_household: false,
      },
      {
        key: 'nameless-child',
        name: '',
        relation: 'child',
        gender_id: null,
        age: null,
        is_deceased: false,
        born_into_id: null,
        born_into_name: '',
        is_household: false,
      },
    ],
    lands: {
      1: {
        title_id: 1,
        land_name: '',
        description: '',
        hall_name: 'the Torre Accesa',
        land_shape_names: ['coast', 'volcanic'],
      },
    },
    estate_name: 'Casa Candela',
    estate_description: 'A townhouse on the merchant terrace.',
  };
}

function template(): HouseTemplateOption {
  return {
    id: 3,
    name: 'Ducal Charter',
    kind: 1,
    aspect_definitions: [],
    features: [],
    holdings: [],
    default_succession_law: null,
    starting_kin_slots: 3,
  };
}

function claimStatus(): HouseClaimStatus {
  return {
    id: 900,
    house_name: 'Candela',
    title_name: 'Fervor',
    status: 'pending',
    aspects: [],
    kin: [],
    lands: [],
    estate_district_id: null,
  };
}

test('the family line quotes every kin, styled and descriptored, a nameless kin reading "to be defined"', () => {
  renderWithProviders(
    <FounderRecord
      draft={draft()}
      characterDraftId={42}
      template={template()}
      quiddityName="The Veiled"
      seatName="Fervor"
      seatTier="duchy"
      swornTo="Piropa"
      landLine="Fervor · 2 baronies · seat Ascua, the Torre Accesa · coast, volcanic · farmland"
      estateLine="Casa Candela · Perdition"
      realmId={1}
      youName="Given name"
      reset={vi.fn()}
      onBack={vi.fn()}
      onSubmitted={vi.fn()}
    />
  );

  expect(
    screen.getByText(
      'Estuosa za Candela · Dario zas Candela, consort · Given name za Candela, heir · a child, to be defined'
    )
  ).toBeInTheDocument();
});

test('Submit for review posts the nested claim payload and reports success up', async () => {
  const onSubmitted = vi.fn();
  const reset = vi.fn();
  vi.mocked(submitHouseClaim).mockResolvedValue(claimStatus());

  renderWithProviders(
    <FounderRecord
      draft={draft()}
      characterDraftId={42}
      template={template()}
      quiddityName="The Veiled"
      seatName="Fervor"
      seatTier="duchy"
      swornTo="Piropa"
      landLine="Fervor · 2 baronies · seat Ascua, the Torre Accesa · coast, volcanic · farmland"
      estateLine="Casa Candela · Perdition"
      realmId={1}
      youName="Given name"
      reset={reset}
      onBack={vi.fn()}
      onSubmitted={onSubmitted}
    />
  );

  await userEvent.click(screen.getByRole('button', { name: 'Submit for review' }));

  expect(submitHouseClaim).toHaveBeenCalledTimes(1);
  const [calledDraftId, payload] = vi.mocked(submitHouseClaim).mock.calls[0];
  expect(calledDraftId).toBe(42);
  expect(payload.kin).toHaveLength(3);
  expect(payload.lands.map((land) => land.title)).toEqual([1]);
  expect(payload.estate.name).toBe('Casa Candela');

  await waitFor(() => {
    expect(reset).toHaveBeenCalled();
    expect(onSubmitted).toHaveBeenCalledWith(claimStatus());
  });
});
