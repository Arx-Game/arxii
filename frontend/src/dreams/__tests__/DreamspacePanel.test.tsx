/** DreamspacePanel (#3003) — the play-view takeover while dreaming. Mocks the module's
 * own queries and the websocket dispatcher. */
import { fireEvent, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { DreamspacePanel } from '../components/DreamspacePanel';
import type { DreamState } from '../types';

const executeActionMock = vi.fn();
vi.mock('@/hooks/useGameSocket', () => ({
  useGameSocket: () => ({
    connect: vi.fn(),
    disconnectAll: vi.fn(),
    send: vi.fn(),
    executeAction: executeActionMock,
  }),
}));

vi.mock('@/dreams/queries', () => ({
  dreamKeys: {
    all: ['dreams'],
    state: (characterId: number) => ['dreams', 'state', characterId],
  },
  useDreamState: vi.fn(),
}));

import { useDreamState } from '@/dreams/queries';

const mockQuery = vi.mocked(useDreamState);

function mockDreamState(overrides: Partial<DreamState>): void {
  const state: DreamState = {
    is_dreamside: false,
    dream_room: null,
    co_dreamers: [],
    dreamwalk_host: null,
    dreamwalk_candidates: [],
    can_descend: false,
    descent_name: '',
    can_ascend: false,
    wake_blocked: false,
    ...overrides,
  };
  mockQuery.mockReturnValue({
    data: state,
    isLoading: false,
  } as ReturnType<typeof useDreamState>);
}

describe('DreamspacePanel', () => {
  it('renders the dream room and co-dreamers', () => {
    mockDreamState({
      is_dreamside: true,
      dream_room: { id: 3, key: 'The Shifting Mists', description: 'Wisps of grey mist.' },
      co_dreamers: [{ id: 9, name: 'Bel' }],
    });
    renderWithProviders(<DreamspacePanel characterId={7} characterName="Aria" />);
    expect(screen.getByText('The Shifting Mists')).toBeInTheDocument();
    expect(screen.getByText('Bel')).toBeInTheDocument();
  });

  it('dispatches wake', () => {
    mockDreamState({ is_dreamside: true, wake_blocked: false });
    renderWithProviders(<DreamspacePanel characterId={7} characterName="Aria" />);
    fireEvent.click(screen.getByRole('button', { name: 'Wake' }));
    expect(executeActionMock).toHaveBeenCalledWith('Aria', 'wake', {});
  });

  it('disables wake with a reason when dream-engaged', () => {
    mockDreamState({ is_dreamside: true, wake_blocked: true });
    renderWithProviders(<DreamspacePanel characterId={7} characterName="Aria" />);
    expect(screen.getByRole('button', { name: 'Wake' })).toBeDisabled();
    expect(screen.getByText(/lost in the dream/i)).toBeInTheDocument();
  });

  it('dispatches dreamwalk with the chosen target', () => {
    mockDreamState({ is_dreamside: true, dreamwalk_candidates: [{ id: 12, name: 'Cyra' }] });
    renderWithProviders(<DreamspacePanel characterId={7} characterName="Aria" />);
    fireEvent.click(screen.getByRole('button', { name: 'Cyra' }));
    expect(executeActionMock).toHaveBeenCalledWith('Aria', 'dreamwalk', { target: 12 });
  });

  it('disables descend with a reason when there is no deeper dream', () => {
    mockDreamState({ is_dreamside: true, can_descend: false });
    renderWithProviders(<DreamspacePanel characterId={7} characterName="Aria" />);
    expect(screen.getByRole('button', { name: /descend/i })).toBeDisabled();
    expect(screen.getByText(/no deeper dream to descend/i)).toBeInTheDocument();
  });

  it('dispatches descend when a deeper dream is available, naming the destination', () => {
    mockDreamState({ is_dreamside: true, can_descend: true, descent_name: 'The Deep Dreaming' });
    renderWithProviders(<DreamspacePanel characterId={7} characterName="Aria" />);
    const button = screen.getByRole('button', { name: /descend to the deep dreaming/i });
    fireEvent.click(button);
    expect(executeActionMock).toHaveBeenCalledWith('Aria', 'descend', {});
  });

  it('disables ascend with a reason when there is no way back', () => {
    mockDreamState({ is_dreamside: true, can_ascend: false });
    renderWithProviders(<DreamspacePanel characterId={7} characterName="Aria" />);
    expect(screen.getByRole('button', { name: 'Ascend' })).toBeDisabled();
    expect(screen.getByText(/cannot find your way back/i)).toBeInTheDocument();
  });

  it('dispatches ascend when available', () => {
    mockDreamState({ is_dreamside: true, can_ascend: true });
    renderWithProviders(<DreamspacePanel characterId={7} characterName="Aria" />);
    fireEvent.click(screen.getByRole('button', { name: 'Ascend' }));
    expect(executeActionMock).toHaveBeenCalledWith('Aria', 'ascend', {});
  });

  it('shows an empty-dream state when no one shares it', () => {
    mockDreamState({ is_dreamside: true, co_dreamers: [] });
    renderWithProviders(<DreamspacePanel characterId={7} characterName="Aria" />);
    expect(screen.getByText(/alone in this dream/i)).toBeInTheDocument();
  });

  it('names the dreamwalk host when the walker arrived via dreamwalk', () => {
    mockDreamState({ is_dreamside: true, dreamwalk_host: { id: 4, name: 'Marren' } });
    renderWithProviders(<DreamspacePanel characterId={7} characterName="Aria" />);
    expect(screen.getByText(/dreamwalked into Marren's dream/i)).toBeInTheDocument();
  });
});
