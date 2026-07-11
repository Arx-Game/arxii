/**
 * Tests for DramaticMomentSuggestionChip — the GM confirm/dismiss inbox chip
 * for PENDING dramatic-moment suggestions (#2183).
 */

import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import type { ReactNode } from 'react';
import type { DramaticMomentSuggestionSummary } from '../../types';

// Mock the low-level fetch seam rather than the exported query fns — the
// mutation hooks close over the module-local confirm/dismiss functions, so
// re-exporting mocked versions from '../../queries' would never be reached.
const mockApiFetch = vi.fn(() =>
  Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response)
);

vi.mock('@/evennia_replacements/api', () => ({
  apiFetch: (...args: unknown[]) => mockApiFetch(...(args as [])),
}));

import { DramaticMomentSuggestionChip } from '../DramaticMomentSuggestionChip';

function makeSuggestion(
  overrides: Partial<DramaticMomentSuggestionSummary> = {}
): DramaticMomentSuggestionSummary {
  return {
    id: 7,
    moment_type_id: 1,
    moment_type_label: 'Grand Entrance',
    character_sheet_id: 10,
    success_level: 2,
    status: 'pending',
    ...overrides,
  };
}

function createWrapper() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return function Wrapper({ children }: { children: ReactNode }) {
    return <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>;
  };
}

describe('DramaticMomentSuggestionChip', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockApiFetch.mockImplementation(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({}) } as Response)
    );
  });

  it('renders nothing when there are no suggestions', () => {
    render(<DramaticMomentSuggestionChip suggestions={[]} sceneId="5" />, {
      wrapper: createWrapper(),
    });
    expect(screen.queryByTestId('dramatic-moment-suggestion-chip')).toBeNull();
  });

  it('renders the chip with the moment type label', () => {
    render(<DramaticMomentSuggestionChip suggestions={[makeSuggestion()]} sceneId="5" />, {
      wrapper: createWrapper(),
    });
    expect(screen.getByTestId('dramatic-moment-suggestion-chip')).toBeInTheDocument();
    expect(screen.getByText(/Grand Entrance/)).toBeInTheDocument();
    expect(screen.getByTestId('dramatic-moment-suggestion-chip-confirm')).toBeInTheDocument();
    expect(screen.getByTestId('dramatic-moment-suggestion-chip-dismiss')).toBeInTheDocument();
  });

  it('clicking confirm POSTs to the confirm endpoint with the suggestion id', async () => {
    const user = userEvent.setup();
    render(
      <DramaticMomentSuggestionChip suggestions={[makeSuggestion({ id: 42 })]} sceneId="5" />,
      {
        wrapper: createWrapper(),
      }
    );

    await user.click(screen.getByTestId('dramatic-moment-suggestion-chip-confirm'));

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        '/api/magic/dramatic-moment-suggestions/42/confirm/',
        {
          method: 'POST',
        }
      )
    );
  });

  it('clicking dismiss POSTs to the dismiss endpoint with the suggestion id', async () => {
    const user = userEvent.setup();
    render(
      <DramaticMomentSuggestionChip suggestions={[makeSuggestion({ id: 42 })]} sceneId="5" />,
      {
        wrapper: createWrapper(),
      }
    );

    await user.click(screen.getByTestId('dramatic-moment-suggestion-chip-dismiss'));

    await waitFor(() =>
      expect(mockApiFetch).toHaveBeenCalledWith(
        '/api/magic/dramatic-moment-suggestions/42/dismiss/',
        {
          method: 'POST',
        }
      )
    );
  });

  it('invalidates the scene-interactions cache on successful confirm', async () => {
    const user = userEvent.setup();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    render(
      <QueryClientProvider client={queryClient}>
        <DramaticMomentSuggestionChip suggestions={[makeSuggestion({ id: 42 })]} sceneId="5" />
      </QueryClientProvider>
    );

    await user.click(screen.getByTestId('dramatic-moment-suggestion-chip-confirm'));

    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['scene-interactions', '5'] })
    );
  });

  it('invalidates the scene-interactions cache on successful dismiss', async () => {
    const user = userEvent.setup();
    const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
    const invalidateSpy = vi.spyOn(queryClient, 'invalidateQueries');

    render(
      <QueryClientProvider client={queryClient}>
        <DramaticMomentSuggestionChip suggestions={[makeSuggestion({ id: 42 })]} sceneId="5" />
      </QueryClientProvider>
    );

    await user.click(screen.getByTestId('dramatic-moment-suggestion-chip-dismiss'));

    await waitFor(() =>
      expect(invalidateSpy).toHaveBeenCalledWith({ queryKey: ['scene-interactions', '5'] })
    );
  });

  it('renders one chip per suggestion', () => {
    render(
      <DramaticMomentSuggestionChip
        suggestions={[
          makeSuggestion({ id: 1, moment_type_label: 'Grand Entrance' }),
          makeSuggestion({ id: 2, moment_type_label: 'Climactic Blow' }),
        ]}
        sceneId="5"
      />,
      { wrapper: createWrapper() }
    );

    expect(screen.getAllByTestId('dramatic-moment-suggestion-chip')).toHaveLength(2);
    expect(screen.getByText(/Grand Entrance/)).toBeInTheDocument();
    expect(screen.getByText(/Climactic Blow/)).toBeInTheDocument();
  });
});
