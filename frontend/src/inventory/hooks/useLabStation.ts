/**
 * Lab station (#1234) react-query hooks.
 *
 * Cache key shape:
 *   ["lab-station"]                    — root key, invalidated by install/upgrade
 *                                         since the resulting feature_instance_id
 *                                         isn't known to the caller beforehand
 *   ["lab-station", featureInstanceId] — status for one station
 */

import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  getLabStationStatus,
  installLabStation,
  repairLabStation,
  upgradeLabStation,
} from '../api';
import type { RepairLabStationPayload } from '../types';

export const labStationKeys = {
  all: ['lab-station'] as const,
  status: (featureInstanceId: number) => ['lab-station', featureInstanceId] as const,
};

export function useLabStationStatus(featureInstanceId: number | undefined) {
  return useQuery({
    queryKey: labStationKeys.status(featureInstanceId ?? -1),
    queryFn: () => getLabStationStatus(featureInstanceId as number),
    enabled: featureInstanceId != null,
  });
}

export function useInstallLabStation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: installLabStation,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: labStationKeys.all }).catch(() => {});
    },
  });
}

export function useUpgradeLabStation() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: upgradeLabStation,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: labStationKeys.all }).catch(() => {});
    },
  });
}

export function useRepairLabStation(featureInstanceId: number) {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (payload: RepairLabStationPayload) => repairLabStation(featureInstanceId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: labStationKeys.status(featureInstanceId) }).catch(() => {});
    },
  });
}
