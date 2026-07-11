import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { getPresence } from '@/presence/api';
import { PresencePanel } from './PresencePanel';

vi.mock('@/presence/api', () => ({ getPresence: vi.fn() }));

// Mock the roster query — component resolves active character → characterId (#2163)
vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: vi.fn(() => ({
    data: [
      {
        id: 1,
        name: 'TestChar',
        character_id: 42,
        profile_picture_url: null,
        primary_persona_id: null,
        active_persona_id: null,
      },
    ],
  })),
}));

// Mock the Redux selector — return the active character name used above
vi.mock('@/store/hooks', () => ({
  useAppSelector: vi.fn((selector: (state: unknown) => unknown) =>
    selector({ game: { active: 'TestChar' }, auth: {} })
  ),
}));

// Mock the combat dispatch hook (Go there travel affordance, #2163)
vi.mock('@/combat/queries', () => ({
  useDispatchPlayerAction: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
  })),
}));

import { useDispatchPlayerAction } from '@/combat/queries';

describe('PresencePanel', () => {
  it('renders the online roster with a coarse idle marker', async () => {
    vi.mocked(getPresence).mockResolvedValue({
      who: [{ name: 'Bram', idle: 'idle' }],
      where: [],
    });
    renderWithProviders(<PresencePanel />);
    expect(await screen.findByText('Bram')).toBeInTheDocument();
    expect(screen.getByText('idle')).toBeInTheDocument();
  });

  it('renders where entries with their location', async () => {
    vi.mocked(getPresence).mockResolvedValue({
      who: [],
      where: [{ persona_name: 'Captain Vale', room_path: 'Umbros - Sable Hold', room_id: 501 }],
    });
    renderWithProviders(<PresencePanel />);
    expect(await screen.findByText('Captain Vale')).toBeInTheDocument();
  });
});

describe('PresencePanel — Go there button (#2163)', () => {
  beforeEach(() => {
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);
  });

  it('renders a Go there control for each where row', async () => {
    vi.mocked(getPresence).mockResolvedValue({
      who: [],
      where: [{ persona_name: 'Captain Vale', room_path: 'Umbros - Sable Hold', room_id: 501 }],
    });

    renderWithProviders(<PresencePanel />);

    expect(await screen.findByTestId('go-there-where-0')).toBeInTheDocument();
  });

  it('dispatches the travel_to registry action with the target room id on click', async () => {
    const user = userEvent.setup();
    const mockMutate = vi.fn();
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);
    vi.mocked(getPresence).mockResolvedValue({
      who: [],
      where: [{ persona_name: 'Captain Vale', room_path: 'Umbros - Sable Hold', room_id: 501 }],
    });

    renderWithProviders(<PresencePanel />);

    const button = await screen.findByTestId('go-there-where-0');
    await user.click(button);

    await waitFor(() => {
      expect(mockMutate).toHaveBeenCalledWith({
        ref: { backend: 'registry', registry_key: 'travel_to' },
        kwargs: { target: 501 },
      });
    });
  });
});
