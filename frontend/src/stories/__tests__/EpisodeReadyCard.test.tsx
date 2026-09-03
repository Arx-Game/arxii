/**
 * EpisodeReadyCard Tests (#3565 fix round 1)
 *
 * ResolveEpisodeDialog was deleted when GM-choice transitions were retired,
 * but the Lead GM's ADVANCE gesture was not: resolve_episode() is only ever
 * called from POST /api/episodes/{id}/resolve/ (plus the telnet action), so
 * the web GM queue still needs a trigger for it. Covers:
 *  - "Advance episode" renders when eligible_transitions is non-empty
 *  - no button when eligible_transitions is empty
 *  - click calls useResolveEpisode with { progress_id } (no chosen_transition,
 *    no picker) and shows a success toast
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { EpisodeReadyCard } from '../components/EpisodeReadyCard';
import type { GMQueueEpisodeEntry } from '../types';

vi.mock('../queries', () => ({
  useResolveEpisode: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: { success: vi.fn(), error: vi.fn() },
}));

import * as queries from '../queries';
import { toast } from 'sonner';

function makeMutationMock() {
  const mutateMock = vi.fn();
  vi.mocked(queries.useResolveEpisode).mockReturnValue({
    mutate: mutateMock,
    mutateAsync: vi.fn(),
    isPending: false,
    isSuccess: false,
    isError: false,
    isIdle: true,
    error: null,
    data: undefined,
    variables: undefined,
    status: 'idle',
    reset: vi.fn(),
    context: undefined,
    failureCount: 0,
    failureReason: null,
    isPaused: false,
    submittedAt: 0,
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
  } as any);
  return mutateMock;
}

const baseEntry: GMQueueEpisodeEntry = {
  story_id: 1,
  story_title: 'Who Am I?',
  scope: 'character',
  episode_id: 20,
  episode_title: 'The Reckoning',
  progress_type: 'character',
  progress_id: 5,
  eligible_transitions: [{ transition_id: 1 }],
  open_session_request_id: null,
};

describe('EpisodeReadyCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders an Advance episode button when transitions are eligible', () => {
    makeMutationMock();
    renderWithProviders(<EpisodeReadyCard entry={baseEntry} />);
    expect(screen.getByTestId('advance-episode-btn')).toBeInTheDocument();
    expect(screen.getByText('1 transition')).toBeInTheDocument();
  });

  it('shows no Advance episode button when there are no eligible transitions', () => {
    makeMutationMock();
    renderWithProviders(<EpisodeReadyCard entry={{ ...baseEntry, eligible_transitions: [] }} />);
    expect(screen.queryByTestId('advance-episode-btn')).not.toBeInTheDocument();
    expect(screen.getByText('No eligible transitions')).toBeInTheDocument();
  });

  it('calls useResolveEpisode with only progress_id on click (no picker, no chosen_transition)', async () => {
    const user = userEvent.setup();
    const mutateMock = makeMutationMock();
    mutateMock.mockImplementation((_vars: unknown, callbacks: Record<string, unknown>) => {
      const cb = callbacks as { onSuccess?: () => void };
      cb.onSuccess?.();
    });

    renderWithProviders(<EpisodeReadyCard entry={baseEntry} />);
    await user.click(screen.getByTestId('advance-episode-btn'));

    expect(mutateMock).toHaveBeenCalledWith(
      {
        episodeId: 20,
        storyId: 1,
        progress_id: 5,
      },
      expect.any(Object)
    );

    await waitFor(() => {
      expect(toast.success).toHaveBeenCalledWith('Episode advanced');
    });
  });
});
