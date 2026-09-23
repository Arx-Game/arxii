import { screen } from '@testing-library/react';
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
