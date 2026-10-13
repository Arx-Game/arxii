import { fireEvent, screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { getPresence } from '@/presence/api';
import { PresencePanel } from './PresencePanel';

vi.mock('@/presence/api', () => ({ getPresence: vi.fn() }));

// PersonaMenu (#4030) wraps every Who row; its own data fetch is mocked the
// same way Task 8's PersonaMenu.test.tsx does — the hardcoded Look/View sheet
// items don't depend on this data, so a bare stub is enough here.
vi.mock('@/game/persona-menu/personaMenuApi', () => ({
  usePersonaMenuQuery: () => ({ data: undefined, isLoading: false }),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

// Mock the roster query — component resolves active character → characterId (#2163);
// #4321 matches the viewer's own Online rows by the worn face (active_persona_id).
vi.mock('@/roster/queries', () => ({
  useMyRosterEntriesQuery: vi.fn(() => ({
    data: [
      {
        id: 1,
        name: 'TestChar',
        character_id: 42,
        profile_picture_url: null,
        primary_persona_id: 7,
        active_persona_id: 7,
      },
    ],
  })),
}));

// Mock the Redux selector — return the active character name used above, and
// the signed-in account the account menu (#4321) renders for.
vi.mock('@/store/hooks', () => ({
  useAppSelector: vi.fn((selector: (state: unknown) => unknown) =>
    selector({
      game: { active: 'TestChar' },
      auth: {
        account: {
          id: 1,
          username: 'tester',
          display_name: 'Tester',
          avatar_url: null,
          is_staff: false,
          can_create_characters: true,
        },
      },
    })
  ),
}));

vi.mock('@/evennia_replacements/queries', () => ({
  useLogout: () => ({ mutate: vi.fn() }),
}));

// Mock the combat dispatch hook (Go there travel affordance, #2163)
vi.mock('@/combat/queries', () => ({
  useDispatchPlayerAction: vi.fn(() => ({
    mutate: vi.fn(),
    isPending: false,
  })),
}));

import { useDispatchPlayerAction } from '@/combat/queries';
import { toast } from 'sonner';

describe('PresencePanel', () => {
  it('renders the online roster with a coarse idle marker', async () => {
    vi.mocked(getPresence).mockResolvedValue({
      who: [{ name: 'Bram', idle: 'idle', persona_id: 11 }],
      where: [],
    });
    renderWithProviders(<PresencePanel />);
    expect(await screen.findByText('Bram')).toBeInTheDocument();
    expect(screen.getByText('idle')).toBeInTheDocument();
  });

  // #4321: your own name in the Online list is the way out of the game to the
  // account menu, in this tab, with the socket kept. Everyone else's row keeps
  // the persona menu.
  it('opens the account menu from your own row and the persona menu from others', async () => {
    const user = userEvent.setup();
    vi.mocked(getPresence).mockResolvedValue({
      who: [
        { name: 'TestChar', idle: '', persona_id: 7 },
        { name: 'Bram', idle: 'idle', persona_id: 11 },
      ],
      where: [],
    });
    renderWithProviders(<PresencePanel />);

    await user.click(await screen.findByRole('button', { name: 'TestChar' }));
    expect(screen.getByRole('menuitem', { name: 'Profile' })).toHaveAttribute('href', '/profile');
    expect(screen.getByRole('menuitem', { name: 'Log Out Account' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Create Character' })).toHaveAttribute(
      'href',
      '/characters/create'
    );
    await user.keyboard('{Escape}');

    await user.click(screen.getByText('Bram'));
    expect(screen.queryByRole('menuitem', { name: 'Profile' })).not.toBeInTheDocument();
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
      expect(mockMutate).toHaveBeenCalledWith(
        {
          ref: { backend: 'registry', registry_key: 'travel_to' },
          kwargs: { target: 501 },
        },
        expect.objectContaining({ onSuccess: expect.any(Function), onError: expect.any(Function) })
      );
    });
  });

  /**
   * #3155: `DispatchActionView` resolves HTTP 200 even for a business-rule
   * rejection (e.g. no path there). Before the fix this `mutate()` call had
   * no result handling at all, so a rejected travel silently did nothing.
   */
  it('toasts the rejection reason when the dispatch resolves success: false', async () => {
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

    await waitFor(() => expect(mockMutate).toHaveBeenCalled());
    const options = mockMutate.mock.calls[0][1] as {
      onSuccess: (result: { success: boolean; message: string }) => void;
    };
    options.onSuccess({ success: false, message: 'No path there.' });

    expect(toast.error).toHaveBeenCalledWith('No path there.');
  });
});

describe('PresencePanel — Who row persona menu (#4030)', () => {
  it('right-click on a Who name opens the menu with Look and View sheet', async () => {
    vi.mocked(getPresence).mockResolvedValue({
      who: [{ name: 'Bram', idle: '', persona_id: 11 }],
      where: [],
    });

    renderWithProviders(<PresencePanel />);
    fireEvent.contextMenu(await screen.findByText('Bram'));

    const menu = await screen.findByRole('menu');
    const labels = within(menu)
      .getAllByRole('menuitem')
      .map((el) => el.textContent);
    expect(labels).toEqual(['Look', 'View sheet']);
  });

  it('left-click on a Who name also opens the menu (leftClick)', async () => {
    const user = userEvent.setup();
    vi.mocked(getPresence).mockResolvedValue({
      who: [{ name: 'Bram', idle: '', persona_id: 11 }],
      where: [],
    });

    renderWithProviders(<PresencePanel />);
    await user.click(await screen.findByRole('button', { name: 'Bram' }));

    expect(await screen.findByRole('menu')).toBeInTheDocument();
  });
});
