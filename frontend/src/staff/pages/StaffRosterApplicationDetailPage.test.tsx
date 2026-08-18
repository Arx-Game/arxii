import { Route, Routes } from 'react-router-dom';
import { screen, waitFor } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { vi } from 'vitest';

import { renderWithProviders } from '@/test/utils/renderWithProviders';
import * as api from '@/staff/api';
import type { RosterApplicationDetail } from '@/staff/types';
import { StaffRosterApplicationDetailPage } from './StaffRosterApplicationDetailPage';

vi.mock('@/staff/api');

function makeApplication(
  overrides: Partial<RosterApplicationDetail> = {}
): RosterApplicationDetail {
  return {
    id: 1,
    character_name: 'Aldric Valentine',
    player_username: 'playerone',
    status: 'pending',
    status_display: 'Pending',
    applied_date: '2026-08-08T00:00:00Z',
    application_text: 'I would love to play this character because...',
    review_notes: '',
    reviewed_date: null,
    policy_review_info: null,
    ...overrides,
  };
}

function renderDetail(id = '1') {
  return renderWithProviders(
    <Routes>
      <Route path="/staff/roster-applications/:id" element={<StaffRosterApplicationDetailPage />} />
    </Routes>,
    { initialEntries: [`/staff/roster-applications/${id}`] }
  );
}

describe('StaffRosterApplicationDetailPage', () => {
  beforeEach(() => {
    vi.resetAllMocks();
  });

  it('renders the application detail from the mock', async () => {
    vi.mocked(api.getRosterApplicationDetail).mockResolvedValue(makeApplication());

    renderDetail();

    expect(await screen.findByText('Aldric Valentine')).toBeInTheDocument();
    expect(screen.getByText('playerone')).toBeInTheDocument();
    expect(screen.getByText('I would love to play this character because...')).toBeInTheDocument();
    expect(api.getRosterApplicationDetail).toHaveBeenCalledWith(1);
  });

  it('renders policy review info as a definition list when present', async () => {
    vi.mocked(api.getRosterApplicationDetail).mockResolvedValue(
      makeApplication({ policy_review_info: { alt_count: 2, flagged: true } })
    );

    renderDetail();

    expect(await screen.findByText('Policy Review')).toBeInTheDocument();
    expect(screen.getByText('Alt Count')).toBeInTheDocument();
    expect(screen.getByText('2')).toBeInTheDocument();
    expect(screen.getByText('Flagged')).toBeInTheDocument();
    expect(screen.getByText('Yes')).toBeInTheDocument();
  });

  it('hides the policy review panel when null', async () => {
    vi.mocked(api.getRosterApplicationDetail).mockResolvedValue(makeApplication());

    renderDetail();

    await screen.findByText('Aldric Valentine');
    expect(screen.queryByText('Policy Review')).not.toBeInTheDocument();
  });

  it('fires the approve mutation without requiring notes', async () => {
    vi.mocked(api.getRosterApplicationDetail).mockResolvedValue(makeApplication());
    vi.mocked(api.reviewRosterApplication).mockResolvedValue({
      action: 'approved',
      tenure_created: true,
    });

    renderDetail();

    await screen.findByText('Aldric Valentine');
    await userEvent.click(screen.getByRole('button', { name: 'Approve' }));

    await waitFor(() => {
      expect(api.reviewRosterApplication).toHaveBeenCalledWith(1, 'approve', '');
    });
  });

  it('requires notes before firing the deny mutation, then sends the typed notes', async () => {
    vi.mocked(api.getRosterApplicationDetail).mockResolvedValue(makeApplication());
    vi.mocked(api.reviewRosterApplication).mockResolvedValue({
      action: 'denied',
      success: true,
    });

    renderDetail();

    await screen.findByText('Aldric Valentine');
    await userEvent.click(screen.getByRole('button', { name: 'Deny' }));

    expect(
      await screen.findByText('Notes are required to deny an application.')
    ).toBeInTheDocument();
    expect(api.reviewRosterApplication).not.toHaveBeenCalled();

    await userEvent.type(screen.getByPlaceholderText(/notes for the applicant/i), 'Not a fit.');
    await userEvent.click(screen.getByRole('button', { name: 'Deny' }));

    await waitFor(() => {
      expect(api.reviewRosterApplication).toHaveBeenCalledWith(1, 'deny', 'Not a fit.');
    });
  });

  it('hides the review panel for a non-pending application', async () => {
    vi.mocked(api.getRosterApplicationDetail).mockResolvedValue(
      makeApplication({
        status: 'approved',
        status_display: 'Approved',
        review_notes: 'Looks great.',
        reviewed_date: '2026-08-10T00:00:00Z',
      })
    );

    renderDetail();

    await screen.findByText('Aldric Valentine');
    expect(screen.queryByRole('button', { name: 'Approve' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Deny' })).not.toBeInTheDocument();
    expect(screen.getByText('Looks great.')).toBeInTheDocument();
  });
});
