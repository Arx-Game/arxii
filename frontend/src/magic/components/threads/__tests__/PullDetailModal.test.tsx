/**
 * Tests for PullDetailModal.
 *
 * Mocks:
 * - @/magic/api (previewPull) to prevent actual API calls from PullEffectPreview
 */

import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import type { ReactNode } from 'react';

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

vi.mock('@/magic/api', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/magic/api')>();
  return {
    ...actual,
    previewPull: vi.fn(),
  };
});

import * as magicApi from '@/magic/api';
import { PullDetailModal } from '../PullDetailModal';
import type { Thread } from '@/magic/types';
import type { PullPreviewResponse } from '@/magic/types';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

function makeThread(overrides: Partial<Thread> = {}): Thread {
  return {
    id: 1,
    owner: 100,
    resonance: 1,
    resonance_name: 'Bene',
    target_kind: 'FACET',
    name: 'Tidal Surge',
    description: '',
    level: 10,
    developed_points: 20,
    path_cap: 30,
    anchor_cap: 30,
    effective_cap: 30,
    retired_at: null,
    created_at: '2025-01-01T00:00:00Z',
    updated_at: '2025-01-02T00:00:00Z',
    ...overrides,
  };
}

function makePreviewResponse(overrides: Partial<PullPreviewResponse> = {}): PullPreviewResponse {
  return {
    resonance_cost: 3,
    anima_cost: 1,
    affordable: true,
    capped_intensity: false,
    resolved_effects: [],
    ...overrides,
  };
}

const mockedPreviewPull = magicApi.previewPull as ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
  mockedPreviewPull.mockResolvedValue(makePreviewResponse());
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PullDetailModal', () => {
  it('renders the modal when open=true', () => {
    render(<PullDetailModal thread={makeThread()} open={true} onOpenChange={() => {}} />, {
      wrapper: createWrapper(),
    });

    expect(screen.getByTestId('pull-detail-modal')).toBeInTheDocument();
  });

  it('does not render dialog content when open=false', () => {
    render(<PullDetailModal thread={makeThread()} open={false} onOpenChange={() => {}} />, {
      wrapper: createWrapper(),
    });

    expect(screen.queryByTestId('pull-detail-modal')).not.toBeInTheDocument();
  });

  it('shows the thread name in the dialog title', () => {
    render(
      <PullDetailModal
        thread={makeThread({ name: 'Vow of the Drowned' })}
        open={true}
        onOpenChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText('Vow of the Drowned')).toBeInTheDocument();
  });

  it('falls back to "Thread #id" when thread has no name', () => {
    render(
      <PullDetailModal
        thread={makeThread({ name: '', id: 42 })}
        open={true}
        onOpenChange={() => {}}
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getByText('Thread #42')).toBeInTheDocument();
  });

  it('renders the PullEffectPreview panel inside the modal', () => {
    render(<PullDetailModal thread={makeThread()} open={true} onOpenChange={() => {}} />, {
      wrapper: createWrapper(),
    });

    // PullEffectPreview renders a data-testid="pull-effect-preview"
    expect(screen.getByTestId('pull-effect-preview')).toBeInTheDocument();
  });

  it('calls onOpenChange(false) when the close button is activated', async () => {
    const onOpenChange = vi.fn();
    render(<PullDetailModal thread={makeThread()} open={true} onOpenChange={onOpenChange} />, {
      wrapper: createWrapper(),
    });

    // Radix Dialog close button has sr-only text "Close"
    const closeBtn = screen.getByRole('button', { name: /close/i });
    await userEvent.click(closeBtn);

    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
