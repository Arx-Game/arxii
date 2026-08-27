/**
 * HubTidingsPanel (#3412 hygiene fold-in) — every FeedItemKind gets a distinct label.
 * Before this fix, every kind except 'deed' fell through to "Scandal".
 */
import { render, screen } from '@testing-library/react';
import { describe, expect, it } from 'vitest';

import { HubTidingsPanel } from './HubTidingsPanel';
import type { HubTidings, HubTidingsItem } from '@/hooks/types';

const KINDS = [
  'deed',
  'scandal',
  'pardon',
  'crisis',
  'proclamation',
  'birthday',
  'stature',
  'menace',
  'verdict',
];

function makeHub(kinds: string[]): HubTidings {
  const items: HubTidingsItem[] = kinds.map((kind, index) => ({
    kind,
    headline: `headline-${index}`,
    subject: `subject-${index}`,
    category: null,
    occurred_at: '2026-06-24T00:00:00Z',
  }));
  return { kind: 'NOTICE_BOARD', name: 'The Notice Board', area_id: null, items };
}

describe('HubTidingsPanel', () => {
  it('renders a distinct label for every FeedItemKind', () => {
    render(<HubTidingsPanel hub={makeHub(KINDS)} />);

    const labels = [
      'Deed',
      'Scandal',
      'Pardon',
      'Crisis',
      'Proclamation',
      'Birthday',
      'Stature',
      'Menace',
      'Verdict',
    ];
    const seen = new Set(labels.map((label) => screen.getByText(label).textContent));
    expect(seen.size).toBe(labels.length);
  });

  it('prefers an authored category label over the kind fallback', () => {
    const hub = makeHub(['deed']);
    hub.items[0].category = 'Treacherous Scandal';
    render(<HubTidingsPanel hub={hub} />);

    expect(screen.getByText('Treacherous Scandal')).toBeInTheDocument();
    expect(screen.queryByText('Deed')).not.toBeInTheDocument();
  });

  it('shows the quiet-day empty state when there are no items', () => {
    render(<HubTidingsPanel hub={makeHub([])} />);

    expect(screen.getByText(/local tidings are quiet today/i)).toBeInTheDocument();
  });
});
