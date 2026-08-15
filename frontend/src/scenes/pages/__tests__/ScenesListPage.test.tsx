import { render, screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { MemoryRouter } from 'react-router-dom';
import type { ReactNode } from 'react';
import type { SceneListItem } from '../../types';

// Mock the roster query — component resolves active character → characterId
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

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

vi.mock('../../queries', async () => {
  const actual = await vi.importActual<typeof import('../../queries')>('../../queries');
  return {
    ...actual,
    fetchScenes: vi.fn(),
  };
});

import { ScenesListPage } from '../ScenesListPage';
import { fetchScenes } from '../../queries';
import { useDispatchPlayerAction } from '@/combat/queries';
import { toast } from 'sonner';

function makeScene(overrides: Partial<SceneListItem> = {}): SceneListItem {
  return {
    id: 1,
    name: 'Test Scene',
    description: '',
    date_started: '2026-01-01T00:00:00Z',
    location: { id: 501, name: 'The Bar' },
    participants: [],
    ...overrides,
  };
}

function createWrapper() {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  });
  return function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={queryClient}>
        <MemoryRouter>{children}</MemoryRouter>
      </QueryClientProvider>
    );
  };
}

describe('ScenesListPage — Go there button (#2163)', () => {
  beforeEach(() => {
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutate: vi.fn(),
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);
  });

  it('renders a Go there button for a scene row with a non-null location', async () => {
    vi.mocked(fetchScenes).mockResolvedValue({ results: [makeScene()] });

    render(<ScenesListPage />, { wrapper: createWrapper() });

    expect(await screen.findByTestId('go-there-1')).toBeInTheDocument();
  });

  it('does not render a Go there button when location is null', async () => {
    vi.mocked(fetchScenes).mockResolvedValue({
      results: [makeScene({ location: null })],
    });

    render(<ScenesListPage />, { wrapper: createWrapper() });

    await screen.findByText('Test Scene');
    expect(screen.queryByTestId('go-there-1')).not.toBeInTheDocument();
  });

  it('dispatches the travel_to registry action with the target room id on click', async () => {
    const user = userEvent.setup();
    const mockMutate = vi.fn();
    vi.mocked(useDispatchPlayerAction).mockReturnValue({
      mutate: mockMutate,
      isPending: false,
    } as unknown as ReturnType<typeof useDispatchPlayerAction>);
    vi.mocked(fetchScenes).mockResolvedValue({ results: [makeScene()] });

    render(<ScenesListPage />, { wrapper: createWrapper() });

    const button = await screen.findByTestId('go-there-1');
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
    vi.mocked(fetchScenes).mockResolvedValue({ results: [makeScene()] });

    render(<ScenesListPage />, { wrapper: createWrapper() });

    const button = await screen.findByTestId('go-there-1');
    await user.click(button);

    await waitFor(() => expect(mockMutate).toHaveBeenCalled());
    const options = mockMutate.mock.calls[0][1] as {
      onSuccess: (result: { success: boolean; message: string }) => void;
    };
    options.onSuccess({ success: false, message: 'No path there.' });

    expect(toast.error).toHaveBeenCalledWith('No path there.');
  });
});
