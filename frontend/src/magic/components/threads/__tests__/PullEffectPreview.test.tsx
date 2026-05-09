import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { PullPreviewResponse, Thread } from '../../../types';

// ---------------------------------------------------------------------------
// Mocks
// ---------------------------------------------------------------------------

vi.mock('@/magic/api', () => ({
  previewPull: vi.fn(),
}));

import * as magicApi from '@/magic/api';
import { PullEffectPreview } from '../PullEffectPreview';

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

const makeThread = (overrides: Partial<Thread> = {}): Thread => ({
  id: 1,
  owner: 100,
  resonance: 1,
  resonance_name: 'Bene',
  target_kind: 'RELATIONSHIP_TRACK',
  name: 'Test Thread',
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
});

const makePreviewResponse = (
  overrides: Partial<PullPreviewResponse> = {}
): PullPreviewResponse => ({
  resonance_cost: 5,
  anima_cost: 2,
  affordable: true,
  capped_intensity: false,
  resolved_effects: [],
  ...overrides,
});

// ---------------------------------------------------------------------------
// Setup
// ---------------------------------------------------------------------------

beforeEach(() => {
  vi.mocked(magicApi.previewPull).mockResolvedValue(makePreviewResponse());
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PullEffectPreview', () => {
  it('renders the component', () => {
    render(<PullEffectPreview thread={makeThread()} />, { wrapper: createWrapper() });
    expect(screen.getByTestId('pull-effect-preview')).toBeInTheDocument();
    expect(screen.getByTestId('tier-radio-1')).toBeInTheDocument();
    expect(screen.getByTestId('tier-radio-2')).toBeInTheDocument();
    expect(screen.getByTestId('tier-radio-3')).toBeInTheDocument();
  });

  it('calls previewPull after debounce on mount (tier=1)', async () => {
    render(<PullEffectPreview thread={makeThread()} />, { wrapper: createWrapper() });

    // Wait for debounce to fire and previewPull to be called
    await waitFor(
      () => {
        expect(magicApi.previewPull).toHaveBeenCalledOnce();
        expect(magicApi.previewPull).toHaveBeenCalledWith({
          character_sheet_id: 100,
          resonance_id: 1,
          tier: 1,
          thread_ids: [1],
        });
      },
      { timeout: 1000 }
    );
  });

  it('refetches when tier changes', async () => {
    render(<PullEffectPreview thread={makeThread()} />, { wrapper: createWrapper() });

    // Initial fetch
    await waitFor(() => expect(magicApi.previewPull).toHaveBeenCalledTimes(1), {
      timeout: 1000,
    });

    // Change to tier 2
    fireEvent.click(screen.getByTestId('tier-radio-2'));

    await waitFor(
      () => {
        expect(magicApi.previewPull).toHaveBeenCalledTimes(2);
        expect(magicApi.previewPull).toHaveBeenLastCalledWith(expect.objectContaining({ tier: 2 }));
      },
      { timeout: 1000 }
    );
  });

  it('shows unaffordable indicator when preview.affordable is false', async () => {
    vi.mocked(magicApi.previewPull).mockResolvedValue(makePreviewResponse({ affordable: false }));

    render(<PullEffectPreview thread={makeThread()} />, { wrapper: createWrapper() });

    await waitFor(
      () => {
        expect(screen.getByTestId('preview-unaffordable')).toBeInTheDocument();
      },
      { timeout: 1000 }
    );
  });

  it('shows capped_intensity warning when capped', async () => {
    vi.mocked(magicApi.previewPull).mockResolvedValue(
      makePreviewResponse({ capped_intensity: true })
    );

    render(<PullEffectPreview thread={makeThread()} />, { wrapper: createWrapper() });

    await waitFor(
      () => {
        expect(screen.getByTestId('preview-capped-intensity')).toBeInTheDocument();
      },
      { timeout: 1000 }
    );
  });

  it('enables Pull Now button for always-in-action anchor kind (RELATIONSHIP_TRACK)', () => {
    render(<PullEffectPreview thread={makeThread({ target_kind: 'RELATIONSHIP_TRACK' })} />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByTestId('pull-now-button')).toBeEnabled();
  });

  it('enables Pull Now button for FACET anchor kind', () => {
    render(<PullEffectPreview thread={makeThread({ target_kind: 'FACET' })} />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByTestId('pull-now-button')).toBeEnabled();
  });

  it('enables Pull Now button for RELATIONSHIP_CAPSTONE anchor kind', () => {
    render(<PullEffectPreview thread={makeThread({ target_kind: 'RELATIONSHIP_CAPSTONE' })} />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByTestId('pull-now-button')).toBeEnabled();
  });

  it('enables Pull Now button for COVENANT_ROLE anchor kind', () => {
    render(<PullEffectPreview thread={makeThread({ target_kind: 'COVENANT_ROLE' })} />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByTestId('pull-now-button')).toBeEnabled();
  });

  it('disables Pull Now button for TRAIT anchor kind and shows combat context note', () => {
    render(<PullEffectPreview thread={makeThread({ target_kind: 'TRAIT' })} />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByTestId('pull-now-button')).toBeDisabled();
    expect(screen.getByTestId('pull-combat-context-note')).toBeInTheDocument();
  });

  it('disables Pull Now button for TECHNIQUE anchor kind', () => {
    render(<PullEffectPreview thread={makeThread({ target_kind: 'TECHNIQUE' })} />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByTestId('pull-now-button')).toBeDisabled();
  });

  it('disables Pull Now button for ROOM anchor kind', () => {
    render(<PullEffectPreview thread={makeThread({ target_kind: 'ROOM' })} />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByTestId('pull-now-button')).toBeDisabled();
  });

  it('renders effects list from preview', async () => {
    vi.mocked(magicApi.previewPull).mockResolvedValue(
      makePreviewResponse({
        resolved_effects: [
          {
            kind: 'FLAT_BONUS',
            authored_value: 5,
            level_multiplier: 1,
            scaled_value: 5,
            vital_target: null,
            source_thread_id: 1,
            source_thread_level: 10,
            source_tier: 1,
            narrative_snippet: 'A flat bonus.',
            inactive: false,
            inactive_reason: null,
          },
        ],
      })
    );

    render(<PullEffectPreview thread={makeThread()} />, { wrapper: createWrapper() });

    await waitFor(
      () => {
        expect(screen.getByTestId('preview-effects-list')).toBeInTheDocument();
        expect(screen.getByTestId('effect-row-FLAT_BONUS')).toBeInTheDocument();
      },
      { timeout: 1000 }
    );
  });

  it('shows inactive_reason for inactive effects', async () => {
    vi.mocked(magicApi.previewPull).mockResolvedValue(
      makePreviewResponse({
        resolved_effects: [
          {
            kind: 'CAPABILITY_GRANT',
            authored_value: null,
            level_multiplier: 1,
            scaled_value: 0,
            vital_target: null,
            source_thread_id: 1,
            source_thread_level: 10,
            source_tier: 1,
            narrative_snippet: '',
            inactive: true,
            inactive_reason: 'Requires higher tier',
          },
        ],
      })
    );

    render(<PullEffectPreview thread={makeThread()} />, { wrapper: createWrapper() });

    await waitFor(
      () => {
        expect(screen.getByTestId('effect-inactive-reason')).toBeInTheDocument();
        expect(screen.getByText('Requires higher tier')).toBeInTheDocument();
      },
      { timeout: 1000 }
    );
  });
});
