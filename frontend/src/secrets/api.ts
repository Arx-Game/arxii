/** Character Secrets REST calls (#1334): the viewer's known secrets about a character. */
import { apiFetch } from '@/evennia_replacements/api';

import type { PaginatedKnownSecretList } from './types';

export async function listKnownSecrets(subjectId: number): Promise<PaginatedKnownSecretList> {
  const res = await apiFetch(`/api/secrets/known/?subject=${subjectId}`);
  if (!res.ok) {
    throw new Error('Failed to load secrets');
  }
  return res.json() as Promise<PaginatedKnownSecretList>;
}
