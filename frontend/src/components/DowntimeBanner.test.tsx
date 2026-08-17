import { screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi, afterEach } from 'vitest';

import { DowntimeBanner } from './DowntimeBanner';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import * as api from '@/evennia_replacements/api';

function mockDowntimeResponse(downtime: unknown) {
  vi.spyOn(api, 'apiFetch').mockResolvedValue({
    ok: true,
    json: async () => ({ downtime }),
  } as Response);
}

describe('DowntimeBanner', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('renders nothing when no downtime is planned', async () => {
    mockDowntimeResponse(null);
    renderWithProviders(<DowntimeBanner />);
    await waitFor(() => {
      expect(screen.getByTestId('downtime-banner-empty')).toBeInTheDocument();
    });
  });

  it('announces an upcoming window with its message', async () => {
    mockDowntimeResponse({
      source: 'staff',
      starts_at: new Date(Date.now() + 2 * 60 * 60 * 1000).toISOString(),
      expected_duration_minutes: 30,
      message: 'Postgres move',
    });
    renderWithProviders(<DowntimeBanner />);
    await waitFor(() => {
      expect(screen.getByTestId('downtime-banner')).toHaveTextContent('Postgres move');
      expect(screen.getByTestId('downtime-banner')).toHaveTextContent('Scheduled downtime');
    });
  });

  it('flips to in-progress copy once the window has started', async () => {
    mockDowntimeResponse({
      source: 'system',
      starts_at: new Date(Date.now() - 60 * 1000).toISOString(),
      expected_duration_minutes: 5,
      message: 'Automatic security update: the server will restart briefly.',
    });
    renderWithProviders(<DowntimeBanner />);
    await waitFor(() => {
      expect(screen.getByTestId('downtime-banner')).toHaveTextContent('Maintenance in progress');
    });
  });

  it('stays hidden for a window further out than the lead time', async () => {
    mockDowntimeResponse({
      source: 'staff',
      starts_at: new Date(Date.now() + 72 * 60 * 60 * 1000).toISOString(),
      expected_duration_minutes: 30,
      message: 'Far-future maintenance',
    });
    renderWithProviders(<DowntimeBanner />);
    await waitFor(() => {
      expect(screen.getByTestId('downtime-banner-empty')).toBeInTheDocument();
    });
  });
});
