import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { store } from '@/store/store';
import { setAccount } from '@/store/authSlice';
import { fetchPlaces, joinPlace, leavePlace } from '../actionQueries';
import { PlaceBar } from './PlaceBar';

vi.mock('@/roster/queries', () => ({ useMyRosterEntriesQuery: () => ({ data: [] }) }));
vi.mock('../actionQueries', () => ({
  fetchPlaces: vi.fn(),
  joinPlace: vi.fn(),
  leavePlace: vi.fn(),
}));

const place = {
  id: 73,
  name: 'The hearth',
  description: 'A quiet corner.',
  viewer_is_present: false,
};

beforeEach(() => {
  vi.clearAllMocks();
  store.dispatch(
    setAccount({
      id: 6,
      username: 'tester',
      display_name: 'Tester',
      last_login: null,
      email: 'tester@example.com',
      email_verified: true,
      can_create_characters: true,
      character_slots: { total: 4, used: 0, activity_total: 4, activity_used: 0, holders: [] },
      is_staff: false,
      is_gm: false,
      available_characters: [],
      pending_applications: [],
      selected_entry_id: null,
      selected_entry: null,
    })
  );
  vi.mocked(fetchPlaces).mockResolvedValue({ results: [place] } as never);
  vi.mocked(joinPlace).mockResolvedValue({} as never);
  vi.mocked(leavePlace).mockResolvedValue({} as never);
});

describe('PlaceBar target menu', () => {
  it('keeps the left-click join behavior and passes typed target context to the menu', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <PlaceBar
        sceneId="scene-22"
        character="Mira"
        currentPlaceId={null}
        actorId={42}
        accountId={6}
      />
    );

    const button = await screen.findByRole('button', { name: 'The hearth' });
    await user.click(button);
    expect(joinPlace).toHaveBeenCalledWith('scene-22', 73);
  });

  it('keeps the current-place left click as the existing leave behavior', async () => {
    const user = userEvent.setup();
    renderWithProviders(
      <PlaceBar
        sceneId="scene-22"
        character="Mira"
        currentPlaceId={73}
        actorId={42}
        accountId={6}
      />
    );

    await user.click(await screen.findByRole('button', { name: 'The hearth' }));
    expect(leavePlace).toHaveBeenCalledWith('scene-22', 73);
  });
});
