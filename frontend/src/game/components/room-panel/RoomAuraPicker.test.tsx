/**
 * RoomAuraPicker tests (#2036) — tag/untag the current room's resonance aura.
 *
 * Mocks `useCharacterResonances` (mirrors MotifStylePanel.test.tsx's
 * mock-the-hook-module idiom) and `dispatchRoomBuilder` (mirrors
 * RoomEditorPanel.test.tsx's mock-the-api-function idiom, since this
 * component drives its mutations with real `useMutation` calls, no msw).
 */

import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { dispatchRoomBuilder } from '@/buildings/api';
import { useCharacterResonances } from '@/magic/queries';
import { RoomAuraPicker } from './RoomAuraPicker';

vi.mock('@/buildings/api', async () => {
  const actual = await vi.importActual<typeof import('@/buildings/api')>('@/buildings/api');
  return { ...actual, dispatchRoomBuilder: vi.fn() };
});

vi.mock('@/magic/queries', () => ({
  useCharacterResonances: vi.fn(),
}));

const mockResonances = [
  {
    id: 3,
    character_sheet: 10,
    resonance: 3,
    resonance_name: 'Starfire',
    resonance_detail: { id: 3, name: 'Starfire' },
    balance: 50,
    lifetime_earned: 200,
  },
  {
    id: 5,
    character_sheet: 10,
    resonance: 5,
    resonance_name: 'Moonveil',
    resonance_detail: { id: 5, name: 'Moonveil' },
    balance: 20,
    lifetime_earned: 80,
  },
];

function setupMocks(resonances: typeof mockResonances = mockResonances) {
  vi.mocked(useCharacterResonances).mockReturnValue({
    data: resonances,
    isLoading: false,
  } as unknown as ReturnType<typeof useCharacterResonances>);
}

describe('RoomAuraPicker', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders the picker under standing (claimed resonances listed)', () => {
    setupMocks();
    renderWithProviders(<RoomAuraPicker characterId={10} roomId={7} />);

    expect(screen.getByTestId('room-aura-picker')).toBeInTheDocument();
    expect(screen.getByTestId('room-aura-select')).toBeInTheDocument();
    expect(screen.getByText('Starfire')).toBeInTheDocument();
    expect(screen.getByText('Moonveil')).toBeInTheDocument();
  });

  it('shows a claim-a-resonance message when the character has none', () => {
    setupMocks([]);
    renderWithProviders(<RoomAuraPicker characterId={10} roomId={7} />);

    expect(screen.getByTestId('room-aura-no-resonances')).toBeInTheDocument();
    expect(screen.queryByTestId('room-aura-select')).not.toBeInTheDocument();
  });

  it('dispatches tag_room_resonance with the selected resonance_id', async () => {
    setupMocks();
    vi.mocked(dispatchRoomBuilder).mockResolvedValue('You tag this room with Starfire.');
    renderWithProviders(<RoomAuraPicker characterId={10} roomId={7} />);

    await userEvent.selectOptions(screen.getByTestId('room-aura-select'), '3');
    await userEvent.click(screen.getByTestId('room-aura-tag'));

    await waitFor(() => {
      expect(dispatchRoomBuilder).toHaveBeenCalledWith(10, 'tag_room_resonance', {
        resonance_id: 3,
      });
    });
  });

  it('dispatches untag_room_resonance with the selected resonance_id when Clear Aura is clicked', async () => {
    setupMocks();
    vi.mocked(dispatchRoomBuilder).mockResolvedValue('You clear this room of Starfire.');
    renderWithProviders(<RoomAuraPicker characterId={10} roomId={7} />);

    await userEvent.selectOptions(screen.getByTestId('room-aura-select'), '5');
    await userEvent.click(screen.getByTestId('room-aura-clear'));

    await waitFor(() => {
      expect(dispatchRoomBuilder).toHaveBeenCalledWith(10, 'untag_room_resonance', {
        resonance_id: 5,
      });
    });
  });

  it('disables Tag Aura and Clear Aura until a resonance is chosen', () => {
    setupMocks();
    renderWithProviders(<RoomAuraPicker characterId={10} roomId={7} />);

    expect(screen.getByTestId('room-aura-tag')).toBeDisabled();
    expect(screen.getByTestId('room-aura-clear')).toBeDisabled();
  });
});
