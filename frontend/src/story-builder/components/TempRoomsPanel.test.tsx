/**
 * TempRoomsPanel (#2450 Fix round 1): `useStoryInstancesQuery` returns a bare
 * array (the endpoint isn't paginated — see `world.gm.story_views`), not a
 * `{results: [...]}` page. Prior to this fix the panel read `data?.results`,
 * which was always `undefined` against the real (unpaginated) response, so
 * the temp-room list silently rendered empty no matter what the API
 * returned. This locks in reading `data` directly, plus that each row's
 * `RoomAccessPanel` gets the row's own server-provided `grants`.
 */
import { screen } from '@testing-library/react';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import type { StoryInstance } from '../types';

import { TempRoomsPanel } from './TempRoomsPanel';

vi.mock('../queries', () => ({
  useStoryInstancesQuery: vi.fn(),
}));

const { useStoryInstancesQuery } = await import('../queries');

function makeInstance(overrides: Partial<StoryInstance> = {}): StoryInstance {
  return {
    id: 1,
    room_id: 11,
    name: 'Goblin Cave',
    status: 'active',
    created_at: '2026-07-18T00:00:00Z',
    grants: [],
    ...overrides,
  };
}

describe('TempRoomsPanel', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders instance rows from a bare array response, not data.results', () => {
    vi.mocked(useStoryInstancesQuery).mockReturnValue({
      data: [makeInstance({ name: 'Goblin Cave' })],
      isLoading: false,
    } as never);

    renderWithProviders(<TempRoomsPanel runAction={vi.fn()} runAccessAction={vi.fn()} />);

    expect(screen.getByText('Goblin Cave')).toBeInTheDocument();
    expect(screen.queryByText('No active temp rooms.')).not.toBeInTheDocument();
  });

  it('shows the empty state when there are truly no instances', () => {
    vi.mocked(useStoryInstancesQuery).mockReturnValue({ data: [], isLoading: false } as never);

    renderWithProviders(<TempRoomsPanel runAction={vi.fn()} runAccessAction={vi.fn()} />);

    expect(screen.getByText('No active temp rooms.')).toBeInTheDocument();
  });

  it("passes each instance's own grants through to its RoomAccessPanel", async () => {
    const { default: userEvent } = await import('@testing-library/user-event');
    vi.mocked(useStoryInstancesQuery).mockReturnValue({
      data: [makeInstance({ room_id: 11, name: 'Goblin Cave', grants: ['Alice'] })],
      isLoading: false,
    } as never);

    renderWithProviders(<TempRoomsPanel runAction={vi.fn()} runAccessAction={vi.fn()} />);

    await userEvent.click(screen.getByTestId('temp-room-row'));

    expect(screen.getByText('Alice')).toBeInTheDocument();
  });
});
