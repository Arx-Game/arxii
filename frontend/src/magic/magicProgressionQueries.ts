import { useQuery } from '@tanstack/react-query';

import * as api from './magicProgressionApi';

export const magicProgressionKeys = {
  all: ['magic', 'progression'] as const,
  view: (characterSheetId?: number) =>
    [...magicProgressionKeys.all, characterSheetId ?? null] as const,
};

export function useMagicProgression(characterSheetId?: number) {
  return useQuery({
    queryKey: magicProgressionKeys.view(characterSheetId),
    queryFn: () => api.getMagicProgression(characterSheetId),
    throwOnError: true,
  });
}
