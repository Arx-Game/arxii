/**
 * DeedPage tests (#3466 Task 10) — the app's first deed view.
 *
 * Renders `DeedPageContent` directly (avoids router param plumbing), mirroring
 * `CovenantDetailPage`'s `CovenantDetailInner` test pattern. `useDeed`/`useHonorDeed`
 * are both mocked from `../../queries` (the same module `DeedPage.tsx` and
 * `HonorForm.tsx` import from) so no real network or QueryClient is involved.
 */
import { render, screen } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import type { UseQueryResult } from '@tanstack/react-query';

import { DeedPageContent } from '../DeedPage';
import type { DeedDetail } from '../../api';

vi.mock('../../queries', () => ({
  useDeed: vi.fn(),
  useHonorDeed: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
    isError: false,
    error: null,
  })),
}));

import * as queries from '../../queries';

const mockUseDeed = vi.mocked(queries.useDeed);

function makeDeed(overrides: Partial<DeedDetail> = {}): DeedDetail {
  return {
    id: 1,
    title: 'Slew the Wyrm of Ashen Vale',
    description: 'A lone stand against the wyrm at the pass.',
    persona: { id: 3, name: 'Foo' },
    base_value: 20,
    ceiling: 100,
    headroom: 80,
    earned_at_level: 4,
    event: { id: 5, title: 'The Ashen Siege', base_value: 100 },
    honors: [],
    can_honor: { allowed: true, reason: null, hares_required: 1, value_added: 10 },
    ...overrides,
  };
}

function setDeed(data: DeedDetail | undefined, isLoading = false) {
  mockUseDeed.mockReturnValue({
    data,
    isLoading,
  } as unknown as UseQueryResult<DeedDetail, Error>);
}

describe('DeedPage', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('shows a loading state while the deed is being fetched', () => {
    setDeed(undefined, true);
    render(<DeedPageContent deedId={1} />);
    expect(screen.getByTestId('deed-page-loading')).toBeInTheDocument();
  });

  it('renders the title, base value, and honors list', () => {
    setDeed(
      makeDeed({
        honors: [
          {
            id: 1,
            honorer: { id: 7, name: 'Bar' },
            value_added: 10,
            hares_spent: 1,
            established_deed: false,
            created_at: '2026-08-30T00:00:00Z',
            journal: { id: 4, title: 'A Great Deed', body: 'They spoke of it for years.' },
          },
        ],
      })
    );
    render(<DeedPageContent deedId={1} />);

    expect(screen.getByText('Slew the Wyrm of Ashen Vale')).toBeInTheDocument();
    expect(screen.getByTestId('deed-base-value')).toHaveTextContent('20');
    expect(screen.getByTestId('honor-row')).toBeInTheDocument();
    expect(screen.getByText('Bar')).toBeInTheDocument();
    expect(screen.getByText('A Great Deed')).toBeInTheDocument();
  });

  it('displays the refusal reason text when can_honor.allowed is false', () => {
    setDeed(
      makeDeed({
        can_honor: {
          allowed: false,
          reason: 'You need an active persona to honor a deed.',
          hares_required: null,
          value_added: null,
        },
      })
    );
    render(<DeedPageContent deedId={1} />);

    // The reason TEXT must be displayed, not merely the absence of a submit button.
    expect(screen.getByText('You need an active persona to honor a deed.')).toBeInTheDocument();
    expect(screen.queryByRole('button', { name: /honor this deed/i })).not.toBeInTheDocument();
  });

  it('handles the null-cost case (rite not configured for the viewer level) without crashing', () => {
    setDeed(
      makeDeed({
        can_honor: {
          allowed: false,
          reason: 'The Rite of Honors is not configured for your level yet.',
          hares_required: null,
          value_added: null,
        },
      })
    );
    render(<DeedPageContent deedId={1} />);
    expect(
      screen.getByText('The Rite of Honors is not configured for your level yet.')
    ).toBeInTheDocument();
  });

  it('renders the honor form (with cost preview) when can_honor.allowed is true', () => {
    setDeed(
      makeDeed({ can_honor: { allowed: true, reason: null, hares_required: 2, value_added: 15 } })
    );
    render(<DeedPageContent deedId={1} />);
    expect(screen.getByRole('button', { name: /honor this deed/i })).toBeInTheDocument();
    expect(screen.getByTestId('honor-form-cost')).toHaveTextContent('2');
  });

  it('renders an empty-honors message when no one has honored the deed yet', () => {
    setDeed(makeDeed({ honors: [] }));
    render(<DeedPageContent deedId={1} />);
    expect(screen.getByTestId('honor-list-empty')).toBeInTheDocument();
  });

  it('renders a not-found state when the deed does not exist', () => {
    setDeed(undefined, false);
    render(<DeedPageContent deedId={999} />);
    expect(screen.getByText(/deed not found/i)).toBeInTheDocument();
  });
});
