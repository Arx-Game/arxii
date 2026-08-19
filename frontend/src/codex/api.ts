/**
 * Codex API functions
 *
 * Every read accepts an optional `characterId` (a roster entry id belonging
 * to the viewer): the backend scopes knowledge - and therefore visibility of
 * restricted entries and their containers - to that character instead of the
 * union of all the account's characters.
 */

import { apiFetch } from '@/evennia_replacements/api';
import type {
  CodexCategoryTree,
  CodexEntryDetail,
  CodexEntryListItem,
  CodexSubject,
  CodexSubjectTreeNode,
} from './types';

const BASE_URL = '/api/codex';

function buildQuery(params: Record<string, string | number | undefined>): string {
  const search = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== undefined) search.set(key, String(value));
  }
  const encoded = search.toString();
  return encoded ? `?${encoded}` : '';
}

export async function getCodexTree(characterId?: number): Promise<CodexCategoryTree[]> {
  const res = await apiFetch(
    `${BASE_URL}/categories/tree/${buildQuery({ character: characterId })}`
  );
  if (!res.ok) {
    throw new Error('Failed to load codex tree');
  }
  return res.json();
}

export async function getSubject(id: number, characterId?: number): Promise<CodexSubject> {
  const res = await apiFetch(
    `${BASE_URL}/subjects/${id}/${buildQuery({ character: characterId })}`
  );
  if (!res.ok) {
    throw new Error('Failed to load subject');
  }
  return res.json();
}

export async function getSubjects(
  categoryId?: number,
  characterId?: number
): Promise<CodexSubject[]> {
  const query = buildQuery({ category: categoryId, character: characterId });
  const res = await apiFetch(`${BASE_URL}/subjects/${query}`);
  if (!res.ok) {
    throw new Error('Failed to load subjects');
  }
  return res.json();
}

export async function getEntries(
  subjectId?: number,
  characterId?: number
): Promise<CodexEntryListItem[]> {
  const query = buildQuery({ subject: subjectId, character: characterId });
  const res = await apiFetch(`${BASE_URL}/entries/${query}`);
  if (!res.ok) {
    throw new Error('Failed to load entries');
  }
  return res.json();
}

export async function getEntry(id: number, characterId?: number): Promise<CodexEntryDetail> {
  const res = await apiFetch(`${BASE_URL}/entries/${id}/${buildQuery({ character: characterId })}`);
  if (!res.ok) {
    throw new Error('Failed to load entry');
  }
  return res.json();
}

export async function searchEntries(
  query: string,
  characterId?: number
): Promise<CodexEntryListItem[]> {
  if (query.length < 2) return [];
  const res = await apiFetch(
    `${BASE_URL}/entries/${buildQuery({ search: query, character: characterId })}`
  );
  if (!res.ok) {
    throw new Error('Failed to search entries');
  }
  return res.json();
}

export async function getFeaturedEntries(): Promise<CodexEntryListItem[]> {
  const res = await apiFetch(`${BASE_URL}/entries/?featured=true`);
  if (!res.ok) {
    throw new Error('Failed to load featured entries');
  }
  return res.json();
}

export async function getSubjectChildren(
  subjectId: number,
  characterId?: number
): Promise<CodexSubjectTreeNode[]> {
  const query = buildQuery({ character: characterId });
  const res = await apiFetch(`${BASE_URL}/subjects/${subjectId}/children/${query}`);
  if (!res.ok) {
    throw new Error('Failed to load subject children');
  }
  return res.json();
}
