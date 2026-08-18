import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import * as api from '@/staff/api';
import type { RosterApplicationListItem } from '@/staff/types';
import { StaffRosterApplicationsPage } from './StaffRosterApplicationsPage';

vi.mock('@/staff/api');

function makeApplication(
  overrides: Partial<RosterApplicationListItem> = {}
): RosterApplicationListItem {
  return {
    id: 1,
    character_name: 'Aldric Valentine',
    player_username: 'playerone',
    status: 'pending',
    status_display: 'Pending',
    applied_date: '2026-08-08T00:00:00Z',
    ...overrides,
  };
}

describe('StaffRosterApplicationsPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('lists pending roster applications by default', async () => {
    vi.mocked(api.getRosterApplications).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [makeApplication()],
    });

    renderWithProviders(<StaffRosterApplicationsPage />);

    expect(await screen.findByText('Aldric Valentine')).toBeInTheDocument();
    expect(screen.getAllByText('Pending')).toHaveLength(2);
    expect(api.getRosterApplications).toHaveBeenCalledWith('pending', 1);
  });

  it('shows an empty state when there are no applications', async () => {
    vi.mocked(api.getRosterApplications).mockResolvedValue({
      count: 0,
      next: null,
      previous: null,
      results: [],
    });

    renderWithProviders(<StaffRosterApplicationsPage />);

    expect(await screen.findByText(/no roster applications found/i)).toBeInTheDocument();
  });

  it('refetches with the new status when the filter changes', async () => {
    vi.mocked(api.getRosterApplications).mockResolvedValue({
      count: 1,
      next: null,
      previous: null,
      results: [makeApplication()],
    });

    renderWithProviders(<StaffRosterApplicationsPage />);

    await screen.findByText('Aldric Valentine');
    await userEvent.click(screen.getByRole('button', { name: 'Approved' }));

    await waitFor(() => {
      expect(api.getRosterApplications).toHaveBeenCalledWith('approved', 1);
    });
  });
});
