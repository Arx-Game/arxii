/**
 * FounderLandsLeaf (#3983 Plan B Task 6, plate F-IV) — `grantsOf` (`steps.ts`)
 * mirrors the backend's `claim_grants`: a claim on Fervor (a duchy) grants
 * its own internal chain (Fervor itself, its seat county Arsura, its seat
 * barony Ascua) plus any houseless, unclaimed barony sworn directly to a
 * chain row (the undefined barony under Arsura) — never a barony belonging
 * to some OTHER county's own chain (Tizón, Solfatara's own seat).
 */
import { useEffect, useState } from 'react';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { FounderLandsLeaf } from '../founder/FounderLandsLeaf';
import type { FounderDraft, FounderLand, UseFounderDraftResult } from '../founder/founderDraft';
import type { LadderRow } from '../types';

vi.mock('../queries', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../queries')>();
  return { ...actual, useLandShapes: () => ({ data: { results: [] } }) };
});

const rows = [
  {
    title_id: 1,
    name: 'Fervor',
    is_defined: true,
    tier: 'duchy',
    level: 50,
    parent_title_id: null,
    house_id: 9,
    house_name: 'Candela',
    state: 'Held',
    is_seat_of: '',
    sworn_to: 'Piropa (crown)',
    demesne: 2,
    vassals: 1,
    claimable: false,
    seat_domain_id: 10,
    comes_with: '',
  },
  {
    title_id: 2,
    name: 'Arsura',
    is_defined: true,
    tier: 'county',
    level: 53,
    parent_title_id: 1,
    house_id: 9,
    house_name: 'Candela',
    state: 'Held',
    is_seat_of: '',
    sworn_to: 'Fervor',
    demesne: 0,
    vassals: 0,
    claimable: false,
    seat_domain_id: 10,
    comes_with: 'Fervor',
  },
  {
    title_id: 3,
    name: 'Ascua',
    is_defined: true,
    tier: 'barony',
    level: 56,
    parent_title_id: 2,
    house_id: 9,
    house_name: 'Candela',
    state: 'Held',
    is_seat_of: 'Fervor',
    sworn_to: 'Fervor',
    demesne: 0,
    vassals: 0,
    claimable: false,
    seat_domain_id: 10,
    comes_with: 'Fervor',
  },
  {
    title_id: 4,
    name: '',
    is_defined: false,
    tier: 'barony',
    level: 56,
    parent_title_id: 2,
    house_id: null,
    house_name: '',
    state: 'Unclaimed',
    is_seat_of: '',
    sworn_to: 'Arsura',
    demesne: 0,
    vassals: 0,
    claimable: true,
    seat_domain_id: 11,
    comes_with: '',
  },
  {
    title_id: 5,
    name: 'Solfatara',
    is_defined: true,
    tier: 'county',
    level: 53,
    parent_title_id: null,
    house_id: null,
    house_name: '',
    state: 'Unclaimed',
    is_seat_of: '',
    sworn_to: 'Piropa (crown)',
    demesne: 0,
    vassals: 0,
    claimable: true,
    seat_domain_id: 12,
    comes_with: '',
  },
  {
    title_id: 6,
    name: 'Tizón',
    is_defined: true,
    tier: 'barony',
    level: 56,
    parent_title_id: 5,
    house_id: null,
    house_name: '',
    state: 'Unclaimed',
    is_seat_of: 'Solfatara',
    sworn_to: 'Solfatara',
    demesne: 0,
    vassals: 0,
    claimable: false,
    seat_domain_id: 12,
    comes_with: 'Solfatara',
  },
] satisfies LadderRow[];

function baseDraft(): FounderDraft {
  return {
    realm_id: 1,
    title_id: 1,
    template_id: 3,
    house_name: 'Candela',
    words: '',
    colors: '',
    sigil_description: '',
    backstory: '',
    aspect_picks: {},
    principles: {},
    founder_relation: 'child',
    founder_is_heir: true,
    kin: [],
    lands: {},
    estate_name: '',
    estate_description: '',
  };
}

/** A small stateful harness (mirrors `FounderHouseChapter.test.tsx`'s own):
 * a real `setLand` so multi-keystroke typing accumulates into `draft.lands`
 * exactly as `useFounderDraft`'s own `setLand` would. `onDraftChange`
 * exposes the latest draft to the test without a second render pass. */
function Harness({
  initial,
  onDraftChange,
}: {
  initial: FounderDraft;
  onDraftChange: (draft: FounderDraft) => void;
}) {
  const [draft, setDraft] = useState(initial);

  useEffect(() => {
    onDraftChange(draft);
  }, [draft, onDraftChange]);

  const setLand: UseFounderDraftResult['setLand'] = (titleId, patch) => {
    setDraft((prev) => {
      const existing: FounderLand = prev.lands[titleId] ?? {
        title_id: titleId,
        land_name: '',
        description: '',
        hall_name: '',
        land_shape_names: [],
      };
      return { ...prev, lands: { ...prev.lands, [titleId]: { ...existing, ...patch } } };
    });
  };

  return (
    <FounderLandsLeaf draft={draft} setLand={setLand} rows={rows} produces={[]} onNext={() => {}} />
  );
}

test('the barony table lists only the granted baronies — the seat and the loose undefined barony, never a different chain', () => {
  const { container } = renderWithProviders(
    <Harness initial={baseDraft()} onDraftChange={() => {}} />
  );

  const dataRows = container.querySelectorAll('table.lad tbody tr');
  expect(dataRows).toHaveLength(2);

  const rowText = Array.from(dataRows).map((row) => row.textContent ?? '');
  expect(rowText.some((text) => text.includes('Ascua'))).toBe(true);
  expect(rowText.some((text) => text.includes('Undefined'))).toBe(true);
  expect(rowText.some((text) => text.includes('Tizón'))).toBe(false);
  expect(rowText.some((text) => text.includes('Solfatara'))).toBe(false);
});

test('naming the undefined barony updates draft.lands[id].land_name', async () => {
  let latestDraft = baseDraft();
  renderWithProviders(
    <Harness
      initial={baseDraft()}
      onDraftChange={(draft) => {
        latestDraft = draft;
      }}
    />
  );

  await userEvent.click(screen.getByRole('button', { name: /expand undefined barony/i }));
  const nameInput = screen.getByLabelText('Name the land');
  await userEvent.type(nameInput, 'Ascua Minor');

  expect(latestDraft.lands[4]?.land_name).toBe('Ascua Minor');
});
