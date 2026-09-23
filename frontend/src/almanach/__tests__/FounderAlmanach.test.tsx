import { screen, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { createMockDraft } from '@/character-creation/__tests__/fixtures';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { FounderAlmanach } from '../founder/FounderAlmanach';
import type { LadderRow } from '../types';

// Fervor (a duchy, already held by Candela) › Solfatara (its own unclaimed
// county) — the fix round 1, Finding 2 scenario: selecting Solfatara must
// show its immediate liege (House Candela, Fervor's holder) ahead of the
// realm crown (House Piropa).
const rows = [
  {
    title_id: 1,
    name: 'Fervor',
    is_defined: true,
    tier: 'duchy',
    level: 56,
    parent_title_id: null,
    house_id: 9,
    house_name: 'Candela',
    state: 'Held',
    is_seat_of: '',
    sworn_to: 'Piropa (crown)',
    demesne: 1,
    vassals: 1,
    claimable: false,
    seat_domain_id: null,
    comes_with: '',
  },
  {
    title_id: 2,
    name: 'Solfatara',
    is_defined: true,
    tier: 'county',
    level: 53,
    parent_title_id: 1,
    house_id: null,
    house_name: '',
    state: 'Unclaimed',
    is_seat_of: '',
    sworn_to: 'Fervor',
    demesne: 1,
    vassals: 0,
    claimable: true,
    seat_domain_id: null,
    comes_with: '',
  },
  // Fervor's own internal chain (its seat county Arsura, its seat barony
  // Ascua) plus a loose unclaimed barony under Arsura — the contents
  // rail's nested "The Land" sub-list test below claims Fervor and expects
  // exactly these four rows, in this order (#3983 Plan B Task 6 fix round 1).
  {
    title_id: 3,
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
    title_id: 4,
    name: 'Ascua',
    is_defined: true,
    tier: 'barony',
    level: 56,
    parent_title_id: 3,
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
    title_id: 5,
    name: '',
    is_defined: false,
    tier: 'barony',
    level: 56,
    parent_title_id: 3,
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
] satisfies LadderRow[];

vi.mock('@/character-creation/queries', () => ({
  useClaimableTitles: () => ({ data: [] }),
  useHouseClaim: () => ({ data: null }),
}));

vi.mock('../queries', () => ({
  useRealms: () => ({
    data: {
      results: [
        {
          id: 1,
          name: 'Inferna',
          formal_name: 'Grand Principality of Inferna',
          default_tithe_pct: 10,
          unclaimed_by_tier: {},
        },
      ],
    },
  }),
  useLadder: () => ({ data: { rows, unclaimed_by_tier: { duchy: 0, county: 1 } } }),
  useCharter: () => ({ data: undefined }),
}));

test('the contents rail renders three .mv groups in plate order, not merged by label', () => {
  const draft = createMockDraft({ id: 501 });
  const { container } = renderWithProviders(<FounderAlmanach draft={draft} />);

  const groups = container.querySelectorAll('.contents .mv');
  expect(groups).toHaveLength(3);

  const labels = Array.from(groups).map((group) => group.querySelector('.label')?.textContent);
  expect(labels).toEqual(['Holdings', 'House', 'Holdings']);

  const thirdGroupItems = Array.from(groups[2].querySelectorAll('li')).map((li) => li.textContent);
  expect(thirdGroupItems).toEqual(['The Land', 'The Estate']);
});

test('selecting a rung whose parent is held shows the immediate liege ahead of the crown', async () => {
  const draft = createMockDraft({ id: 502 });
  renderWithProviders(<FounderAlmanach draft={draft} />);

  await userEvent.click(screen.getByRole('button', { name: /select solfatara/i }));

  const headings = screen.getAllByRole('heading', { level: 4 }).map((h) => h.textContent);
  const candelaIndex = headings.indexOf('House Candela');
  const piropaIndex = headings.indexOf('House Piropa');
  expect(candelaIndex).toBeGreaterThanOrEqual(0);
  expect(piropaIndex).toBeGreaterThan(candelaIndex);
});

test('the Land rail entry nests the granted rungs in chain-then-extras order, .cur on the currently open one', async () => {
  const draft = createMockDraft({ id: 503 });
  // A claim on Fervor already on record — `useFounderDraft` reads this
  // straight out of localStorage, so the rail's nested list (gated on
  // `fd.title_id != null`) is live from first render, no click-through-
  // the-Seat-step setup needed.
  window.localStorage.setItem(
    'almanach-founder-503',
    JSON.stringify({ title_id: 1, realm_id: 1, template_id: null })
  );

  const { container } = renderWithProviders(<FounderAlmanach draft={draft} />);

  const landGroup = container.querySelectorAll('.contents .mv')[2] as HTMLElement;
  const nestedItems = Array.from(landGroup.querySelectorAll('li ol li')).map(
    (li) => li.textContent
  );
  // grantsOf(rows, Fervor) = chain [Fervor, Arsura, Ascua] then the loose
  // extra (the undefined barony under Arsura) — four entries, matching the
  // brief's own Fervor worked example.
  expect(nestedItems).toEqual(['Fervor', 'Arsura', 'Ascua', 'Undefined']);

  // Nothing is "open" yet (the founder hasn't reached the Land step or
  // clicked a rung), so no nested entry carries `.cur`.
  expect(landGroup.querySelectorAll('li ol li.cur')).toHaveLength(0);

  await userEvent.click(within(landGroup).getByRole('button', { name: 'Ascua' }));

  const ascuaLi = Array.from(landGroup.querySelectorAll('li ol li')).find(
    (li) => li.textContent === 'Ascua'
  );
  expect(ascuaLi).toHaveClass('cur');

  const landTopLi = Array.from(landGroup.querySelectorAll(':scope > ol > li')).find((li) =>
    li.textContent?.startsWith('The Land')
  );
  expect(landTopLi).toHaveClass('cur');
});
