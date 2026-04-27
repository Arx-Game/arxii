/**
 * BeatRow Tests — Task 12.1
 *
 * Covers:
 *  - Mark button renders when beat.can_mark=true and beat is unsatisfied gm_marked
 *  - Mark button is hidden when beat.can_mark=false
 *  - Mark button is hidden when beat is already resolved (even if can_mark=true)
 *  - Contribute button renders for aggregate beats with characterSheetId
 *  - Deadline text renders for beats with a deadline
 */

import { render, screen } from '@testing-library/react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import { vi } from 'vitest';
import type { ReactNode } from 'react';
import { BeatRow } from '../components/BeatRow';
import type { Beat } from '../types';

// ---------------------------------------------------------------------------
// Mocks — suppress dialog internals
// ---------------------------------------------------------------------------

vi.mock('../components/MarkBeatDialog', () => ({
  MarkBeatDialog: () => <button data-testid="mark-beat-dialog-trigger">Mark</button>,
}));

vi.mock('../components/ContributeBeatDialog', () => ({
  ContributeBeatDialog: () => (
    <button data-testid="contribute-beat-dialog-trigger">Contribute</button>
  ),
}));

// ---------------------------------------------------------------------------
// Wrapper
// ---------------------------------------------------------------------------

function createWrapper() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={qc}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

// ---------------------------------------------------------------------------
// Fixtures
// ---------------------------------------------------------------------------

function makeGmMarkedBeat(overrides: Partial<Beat> = {}): Beat {
  return {
    id: 1,
    episode: 10,
    episode_title: 'Test Episode',
    chapter_title: 'Test Chapter',
    story_id: 5,
    story_title: 'Test Story',
    predicate_type: 'gm_marked',
    outcome: 'unsatisfied',
    visibility: 'hinted',
    internal_description: 'The villain confronts the hero',
    player_hint: 'Confront the villain',
    player_resolution_text: undefined,
    order: 1,
    required_level: undefined,
    required_achievement: undefined,
    required_condition_template: undefined,
    required_codex_entry: undefined,
    referenced_story: undefined,
    referenced_milestone_type: undefined,
    referenced_chapter: undefined,
    referenced_episode: undefined,
    required_points: undefined,
    agm_eligible: false,
    deadline: undefined,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-04-19T00:00:00Z',
    can_mark: false,
    ...overrides,
  };
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('BeatRow — can_mark gating', () => {
  it('renders Mark button when can_mark=true and beat is unsatisfied', () => {
    const beat = makeGmMarkedBeat({ can_mark: true });
    render(<BeatRow beat={beat} />, { wrapper: createWrapper() });
    expect(screen.getByTestId('mark-beat-dialog-trigger')).toBeInTheDocument();
  });

  it('hides Mark button when can_mark=false', () => {
    const beat = makeGmMarkedBeat({ can_mark: false });
    render(<BeatRow beat={beat} />, { wrapper: createWrapper() });
    expect(screen.queryByTestId('mark-beat-dialog-trigger')).not.toBeInTheDocument();
  });

  it('hides Mark button when beat is resolved even if can_mark=true', () => {
    const beat = makeGmMarkedBeat({ can_mark: true, outcome: 'success' });
    render(<BeatRow beat={beat} />, { wrapper: createWrapper() });
    expect(screen.queryByTestId('mark-beat-dialog-trigger')).not.toBeInTheDocument();
  });

  it('hides Mark button for non-gm_marked beat type even if can_mark=true', () => {
    const beat = makeGmMarkedBeat({ can_mark: true, predicate_type: 'aggregate_threshold' });
    render(<BeatRow beat={beat} />, { wrapper: createWrapper() });
    expect(screen.queryByTestId('mark-beat-dialog-trigger')).not.toBeInTheDocument();
  });
});

describe('BeatRow — contribute button visibility', () => {
  it('renders Contribute button for aggregate beat with characterSheetId', () => {
    const beat = makeGmMarkedBeat({
      predicate_type: 'aggregate_threshold',
      required_points: 100,
      can_mark: false,
    });
    render(<BeatRow beat={beat} characterSheetId={42} />, { wrapper: createWrapper() });
    expect(screen.getByTestId('contribute-beat-dialog-trigger')).toBeInTheDocument();
  });

  it('hides Contribute button when characterSheetId is null', () => {
    const beat = makeGmMarkedBeat({
      predicate_type: 'aggregate_threshold',
      required_points: 100,
      can_mark: false,
    });
    render(<BeatRow beat={beat} characterSheetId={null} />, { wrapper: createWrapper() });
    expect(screen.queryByTestId('contribute-beat-dialog-trigger')).not.toBeInTheDocument();
  });
});

describe('BeatRow — deadline display', () => {
  it('shows relative deadline text when deadline is set and beat is unsatisfied', () => {
    const futureDate = new Date(Date.now() + 86400000).toISOString();
    const beat = makeGmMarkedBeat({ deadline: futureDate });
    render(<BeatRow beat={beat} />, { wrapper: createWrapper() });
    expect(screen.getByText(/expires/i)).toBeInTheDocument();
  });
});
