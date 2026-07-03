/**
 * LabStationStatusCard component tests.
 */

import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { describe, expect, it, vi, beforeEach } from 'vitest';
import { renderWithProviders } from '@/test/utils/renderWithProviders';
import { LabStationStatusCard } from '../LabStationStatusCard';

// ---------------------------------------------------------------------------
// Module mocks
// ---------------------------------------------------------------------------

vi.mock('../../hooks/useLabStation', () => ({
  useLabStationStatus: vi.fn(),
  useRepairLabStation: vi.fn(),
}));

vi.mock('sonner', () => ({
  toast: {
    success: vi.fn(),
    error: vi.fn(),
  },
}));

import * as labStationHooks from '../../hooks/useLabStation';
import { toast } from 'sonner';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeRepairMock() {
  const mutate = vi.fn();
  vi.mocked(labStationHooks.useRepairLabStation).mockReturnValue({
    mutate,
    mutateAsync: vi.fn(),
    isPending: false,
    isSuccess: false,
    isError: false,
    isIdle: true,
    error: null,
    data: undefined,
    variables: undefined,
    status: 'idle',
    reset: vi.fn(),
    context: undefined,
    failureCount: 0,
    failureReason: null,
    isPaused: false,
    submittedAt: 0,
  } as unknown as ReturnType<typeof labStationHooks.useRepairLabStation>);
  return mutate;
}

function mockStatus(data: unknown, overrides: Partial<{ isLoading: boolean }> = {}) {
  vi.mocked(labStationHooks.useLabStationStatus).mockReturnValue({
    data,
    isLoading: overrides.isLoading ?? false,
    isError: false,
    error: null,
  } as unknown as ReturnType<typeof labStationHooks.useLabStationStatus>);
}

const FEATURE_INSTANCE_ID = 5;

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('LabStationStatusCard', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('renders a "no station" message when featureInstanceId is null', () => {
    makeRepairMock();
    mockStatus(undefined);

    renderWithProviders(<LabStationStatusCard featureInstanceId={null} />);

    expect(screen.getByText(/no lab station in this room/i)).toBeInTheDocument();
  });

  it('renders the durability bar for a healthy station', () => {
    makeRepairMock();
    mockStatus({ durability: 15, max_durability: 20, level: 1, is_broken: false });

    renderWithProviders(<LabStationStatusCard featureInstanceId={FEATURE_INSTANCE_ID} />);

    const card = screen.getByTestId('lab-station-status-card');
    expect(card).toHaveTextContent('15/20');
    expect(card).not.toHaveTextContent('broken');
    // Radix Progress exposes its value via the progressbar role.
    expect(screen.getByRole('progressbar')).toBeInTheDocument();
  });

  it('renders broken-state messaging when is_broken is true', () => {
    makeRepairMock();
    mockStatus({ durability: 0, max_durability: 20, level: 1, is_broken: true });

    renderWithProviders(<LabStationStatusCard featureInstanceId={FEATURE_INSTANCE_ID} />);

    const card = screen.getByTestId('lab-station-status-card');
    expect(card).toHaveTextContent('(broken)');
  });

  it('shows a loading state while status is pending', () => {
    makeRepairMock();
    mockStatus(undefined, { isLoading: true });

    renderWithProviders(<LabStationStatusCard featureInstanceId={FEATURE_INSTANCE_ID} />);

    expect(screen.getByText(/loading station status/i)).toBeInTheDocument();
  });

  it('disables the repair button when durability is already full', () => {
    makeRepairMock();
    mockStatus({ durability: 20, max_durability: 20, level: 1, is_broken: false });

    renderWithProviders(<LabStationStatusCard featureInstanceId={FEATURE_INSTANCE_ID} />);

    expect(screen.getByRole('button', { name: /repair/i })).toBeDisabled();
  });

  it('calls repair mutate with the missing durability on click and toasts on success', async () => {
    const user = userEvent.setup();
    const mutate = makeRepairMock();
    mutate.mockImplementation(
      (
        _vars: unknown,
        callbacks: { onSuccess?: (r: unknown) => void; onError?: (e: unknown) => void }
      ) => {
        callbacks?.onSuccess?.({ durability: 20, max_durability: 20 });
      }
    );
    mockStatus({ durability: 15, max_durability: 20, level: 1, is_broken: false });

    renderWithProviders(<LabStationStatusCard featureInstanceId={FEATURE_INSTANCE_ID} />);

    await user.click(screen.getByRole('button', { name: /repair/i }));

    expect(mutate).toHaveBeenCalledWith({ restore_points: 5 }, expect.any(Object));
    expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('repaired'));
  });

  it('calls the onRepaired callback on a successful repair (#1234 review finding)', async () => {
    const user = userEvent.setup();
    const mutate = makeRepairMock();
    mutate.mockImplementation(
      (
        _vars: unknown,
        callbacks: { onSuccess?: (r: unknown) => void; onError?: (e: unknown) => void }
      ) => {
        callbacks?.onSuccess?.({ durability: 20, max_durability: 20 });
      }
    );
    mockStatus({ durability: 15, max_durability: 20, level: 1, is_broken: false });
    const onRepaired = vi.fn();

    renderWithProviders(
      <LabStationStatusCard featureInstanceId={FEATURE_INSTANCE_ID} onRepaired={onRepaired} />
    );

    await user.click(screen.getByRole('button', { name: /repair/i }));

    expect(onRepaired).toHaveBeenCalledTimes(1);
  });

  it('does not blow up on repair success when onRepaired is not provided', async () => {
    const user = userEvent.setup();
    const mutate = makeRepairMock();
    mutate.mockImplementation(
      (
        _vars: unknown,
        callbacks: { onSuccess?: (r: unknown) => void; onError?: (e: unknown) => void }
      ) => {
        callbacks?.onSuccess?.({ durability: 20, max_durability: 20 });
      }
    );
    mockStatus({ durability: 15, max_durability: 20, level: 1, is_broken: false });

    renderWithProviders(<LabStationStatusCard featureInstanceId={FEATURE_INSTANCE_ID} />);

    await user.click(screen.getByRole('button', { name: /repair/i }));

    expect(toast.success).toHaveBeenCalledWith(expect.stringContaining('repaired'));
  });
});
