import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter, Route, Routes } from 'react-router-dom';
import type { ReactNode } from 'react';

import { BattleWriteupPage } from './BattleWriteupPage';
import type { BattleDeed, BattleDetail } from '../types';

// Mock the query hook
vi.mock('../queries', () => ({
  useBattleDetailQuery: vi.fn(),
}));

import { useBattleDetailQuery } from '../queries';

function makeWrapper(): ReactNode {
  return (
    <QueryClientProvider client={new QueryClient()}>
      <MemoryRouter initialEntries={['/battles/42']}>
        <Routes>
          <Route path="/battles/:id" element={<BattleWriteupPage />} />
          <Route path="/scenes/:id" element={<div data-testid="scene-page" />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>
  );
}

const MOCK_BATTLE: BattleDetail = {
  id: 42,
  name: 'Siege of the Gate',
  outcome: 'attacker_decisive',
  risk_level: 'high',
  is_paused: false,
  round: null,
  sides: [
    {
      id: 1,
      role: 'attacker',
      victory_points: 8,
      victory_threshold: 10,
      posture: 'aggressive',
      covenant_id: 1,
      covenant_name: 'Iron Vanguard',
    },
    {
      id: 2,
      role: 'defender',
      victory_points: 2,
      victory_threshold: 10,
      posture: 'defensive',
      covenant_id: null,
      covenant_name: null,
    },
  ],
  places: [
    {
      id: 1,
      name: 'The Ford',
      terrain_type: 'flooded',
      movement_cost: 2,
      x: 10.5,
      y: -3.0,
      footprint_radius: 2.0,
      controlled_by_id: 1,
      encounter_scene_id: null,
      vehicle: null,
      fortifications: [],
    },
  ],
  units: [
    {
      id: 1,
      name: 'Vanguard Pikes',
      descriptor: 'pike-and-shot',
      quality: 'veteran',
      status: 'active',
      strength: 80,
      morale: 60,
      individual_count: 1,
      side_id: 1,
      place_id: 1,
    },
  ],
  participants: [
    {
      id: 1,
      status: 'active',
      side_id: 1,
      place_id: 1,
      persona: {
        id: 1,
        name: 'Sir Roland',
        thumbnail_url: null,
        thumbnail_media_url: null,
      },
    },
  ],
  // Writeup fields
  concluded_at: '2026-07-10T12:00:00Z',
  created_at: '2026-07-09T08:00:00Z',
  campaign_story_id: null,
  scene_id: 99,
} as unknown as BattleDetail;

const MOCK_DEEDS: BattleDeed[] = [
  {
    id: 1,
    title: 'Slew the enemy commander',
    description: 'A decisive strike.',
    base_value: 50,
    created_at: '2026-07-10T11:00:00Z',
    persona: { id: 1, name: 'Sir Roland' },
  },
];

describe('BattleWriteupPage', () => {
  it('renders loading state', () => {
    vi.mocked(useBattleDetailQuery).mockReturnValue({
      data: undefined,
      isLoading: true,
      isError: false,
    } as unknown as ReturnType<typeof useBattleDetailQuery>);

    render(<BattleWriteupPage />, {
      wrapper: () => makeWrapper() as ReactNode,
    });
    expect(screen.getByTestId('battle-writeup-loading')).toBeInTheDocument();
  });

  it('renders error state', () => {
    vi.mocked(useBattleDetailQuery).mockReturnValue({
      data: undefined,
      isLoading: false,
      isError: true,
    } as unknown as ReturnType<typeof useBattleDetailQuery>);

    render(<BattleWriteupPage />, {
      wrapper: () => makeWrapper() as ReactNode,
    });
    expect(screen.getByTestId('battle-writeup-error')).toBeInTheDocument();
  });

  it('renders battle name, outcome, and metadata', () => {
    vi.mocked(useBattleDetailQuery).mockReturnValue({
      data: { ...MOCK_BATTLE, deeds: [] } as unknown as BattleDetail,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useBattleDetailQuery>);

    render(<BattleWriteupPage />, {
      wrapper: () => makeWrapper() as ReactNode,
    });
    expect(screen.getByTestId('battle-writeup-page')).toBeInTheDocument();
    expect(screen.getByText('Siege of the Gate')).toBeInTheDocument();
    expect(screen.getByTestId('battle-writeup-outcome')).toHaveTextContent('Attacker — decisive');
    expect(screen.getByTestId('battle-writeup-scene-link')).toHaveAttribute('href', '/scenes/99');
  });

  it('renders sides with covenant names and participants', () => {
    vi.mocked(useBattleDetailQuery).mockReturnValue({
      data: { ...MOCK_BATTLE, deeds: [] } as unknown as BattleDetail,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useBattleDetailQuery>);

    render(<BattleWriteupPage />, {
      wrapper: () => makeWrapper() as ReactNode,
    });
    expect(screen.getByText('Iron Vanguard')).toBeInTheDocument();
    expect(screen.getByText('Sir Roland')).toBeInTheDocument();
  });

  it('renders deeds when present', () => {
    vi.mocked(useBattleDetailQuery).mockReturnValue({
      data: { ...MOCK_BATTLE, deeds: MOCK_DEEDS } as unknown as BattleDetail,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useBattleDetailQuery>);

    render(<BattleWriteupPage />, {
      wrapper: () => makeWrapper() as ReactNode,
    });
    expect(screen.getByTestId('battle-writeup-deeds')).toBeInTheDocument();
    expect(screen.getByText('Slew the enemy commander')).toBeInTheDocument();
  });

  it('renders empty deeds state when no deeds', () => {
    vi.mocked(useBattleDetailQuery).mockReturnValue({
      data: { ...MOCK_BATTLE, deeds: [] } as unknown as BattleDetail,
      isLoading: false,
      isError: false,
    } as unknown as ReturnType<typeof useBattleDetailQuery>);

    render(<BattleWriteupPage />, {
      wrapper: () => makeWrapper() as ReactNode,
    });
    expect(screen.getByTestId('battle-writeup-deeds-empty')).toBeInTheDocument();
  });
});
