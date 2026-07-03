import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { act, renderHook, waitFor } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import * as api from '../../api';
import {
  labStationKeys,
  useInstallLabStation,
  useLabStationStatus,
  useRepairLabStation,
} from '../useLabStation';

vi.mock('../../api');

beforeEach(() => {
  vi.clearAllMocks();
});

function createWrapper(qc: QueryClient) {
  return ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
}

const STATION_DETAILS = {
  durability: 15,
  max_durability: 20,
  level: 1,
  is_broken: false,
};

// install/upgrade only start a Project — they return {project_id}, not a
// LabStationDetails row (see world/items/serializers_station.py
// RoomFeatureProjectStartResultSerializer).
const PROJECT_START_RESULT = { project_id: 42 };

// repair returns only the two durability fields, not the full
// LabStationDetails shape (LabStationRepairResultSerializer).
const REPAIR_RESULT = { durability: 15, max_durability: 20 };

describe('useLabStationStatus', () => {
  it('loads station status for a given feature instance id', async () => {
    const qc = new QueryClient();
    vi.mocked(api.getLabStationStatus).mockResolvedValue(STATION_DETAILS);

    const { result } = renderHook(() => useLabStationStatus(7), {
      wrapper: createWrapper(qc),
    });

    expect(result.current.isLoading).toBe(true);
    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.getLabStationStatus).toHaveBeenCalledWith(7);
    expect(result.current.data).toEqual(STATION_DETAILS);
  });

  it('does not fetch when featureInstanceId is undefined', () => {
    const qc = new QueryClient();
    const { result } = renderHook(() => useLabStationStatus(undefined), {
      wrapper: createWrapper(qc),
    });

    expect(result.current.fetchStatus).toBe('idle');
    expect(api.getLabStationStatus).not.toHaveBeenCalled();
  });
});

describe('useInstallLabStation', () => {
  it('installs a station and invalidates the lab-station root key on success', async () => {
    const qc = new QueryClient();
    const invalidate = vi.spyOn(qc, 'invalidateQueries');
    vi.mocked(api.installLabStation).mockResolvedValue(PROJECT_START_RESULT);

    const { result } = renderHook(() => useInstallLabStation(), {
      wrapper: createWrapper(qc),
    });
    await act(async () => {
      await result.current.mutateAsync({ room_profile_id: 3, target_level: 1 });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.installLabStation).toHaveBeenCalledWith({ room_profile_id: 3, target_level: 1 });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: labStationKeys.all });
  });
});

describe('useRepairLabStation', () => {
  it('repairs a station and invalidates that station status query on success', async () => {
    const qc = new QueryClient();
    const invalidate = vi.spyOn(qc, 'invalidateQueries');
    vi.mocked(api.repairLabStation).mockResolvedValue(REPAIR_RESULT);

    const { result } = renderHook(() => useRepairLabStation(7), {
      wrapper: createWrapper(qc),
    });
    await act(async () => {
      await result.current.mutateAsync({ restore_points: 5 });
    });

    await waitFor(() => expect(result.current.isSuccess).toBe(true));
    expect(api.repairLabStation).toHaveBeenCalledWith(7, { restore_points: 5 });
    expect(invalidate).toHaveBeenCalledWith({ queryKey: labStationKeys.status(7) });
  });
});
