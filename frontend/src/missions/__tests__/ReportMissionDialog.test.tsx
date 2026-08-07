/**
 * #1753/#3040 — ReportMissionDialog tests.
 *
 * Verifies the trigger opens the dialog, every offered style renders, the
 * submit button dispatches the mutation with the chosen style, and a
 * mutation error (the server's co-location / not-RESOLVED / not-offerable
 * message) surfaces inline rather than being swallowed.
 */
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import type { ReactNode } from 'react';
import { vi } from 'vitest';

const reportMock = vi.fn();
let mockError: Error | null = null;

vi.mock('../queries', async () => {
  const actual = await vi.importActual<typeof import('../queries')>('../queries');
  return {
    ...actual,
    useReportMission: () => ({
      mutate: reportMock,
      reset: vi.fn(),
      isPending: false,
      error: mockError,
    }),
  };
});

import { ReportMissionDialog } from '../components/ReportMissionDialog';

function withProviders(children: ReactNode) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: 0 } } });
  return <QueryClientProvider client={qc}>{children}</QueryClientProvider>;
}

describe('ReportMissionDialog', () => {
  beforeEach(() => {
    reportMock.mockClear();
    mockError = null;
  });

  it('opens the dialog and lists every report style on trigger click', async () => {
    const user = userEvent.setup();
    render(withProviders(<ReportMissionDialog instanceId={7} templateName="The Lost Ledger" />));

    await user.click(screen.getByTestId('report-mission-7'));

    expect(screen.getByText('Report The Lost Ledger')).toBeInTheDocument();
    expect(screen.getByText('Accurate')).toBeInTheDocument();
    expect(screen.getByText('Humble')).toBeInTheDocument();
    expect(screen.getByText('Mostly accurate')).toBeInTheDocument();
    expect(screen.getByText('Embellished')).toBeInTheDocument();
  });

  it('submits the selected style', async () => {
    const user = userEvent.setup();
    render(withProviders(<ReportMissionDialog instanceId={7} templateName="The Lost Ledger" />));

    await user.click(screen.getByTestId('report-mission-7'));
    await user.click(screen.getByRole('radio', { name: /humble/i }));
    await user.click(screen.getByTestId('report-mission-submit'));

    expect(reportMock).toHaveBeenCalledWith(
      { instanceId: 7, style: 'humble' },
      expect.objectContaining({ onSuccess: expect.any(Function) })
    );
  });

  it('surfaces a mutation error inline (e.g. not co-located with the report-to NPC)', async () => {
    mockError = new Error('You must find a Threshold Warden to report to.');
    const user = userEvent.setup();
    render(withProviders(<ReportMissionDialog instanceId={7} templateName="The Lost Ledger" />));

    await user.click(screen.getByTestId('report-mission-7'));

    expect(screen.getByTestId('report-mission-error')).toHaveTextContent(
      'You must find a Threshold Warden to report to.'
    );
  });
});
