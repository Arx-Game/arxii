/**
 * Codex API functions
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

export async function getCodexTree(): Promise<CodexCategoryTree[]> {
  const res = await apiFetch(`${BASE_URL}/categories/tree/`);
  if (!res.ok) {
    throw new Error('Failed to load codex tree');
  }
  return res.json();
}

export async function getCategory(id: number): Promise<CodexCategoryTree> {
  const res = await apiFetch(`${BASE_URL}/categories/${id}/`);
  if (!res.ok) {
    throw new Error('Failed to load category');
  }
  return res.json();
}

export async function getSubject(id: number): Promise<CodexSubject> {
  const res = await apiFetch(`${BASE_URL}/subjects/${id}/`);
  if (!res.ok) {
    throw new Error('Failed to load subject');
  }
  return res.json();
}

export async function getSubjects(categoryId?: number): Promise<CodexSubject[]> {
  const params = categoryId ? `?category=${categoryId}` : '';
  const res = await apiFetch(`${BASE_URL}/subjects/${params}`);
  if (!res.ok) {
    throw new Error('Failed to load subjects');
  }
  return res.json();
}

export async function getEntries(subjectId?: number): Promise<CodexEntryListItem[]> {
  const params = subjectId ? `?subject=${subjectId}` : '';
  const res = await apiFetch(`${BASE_URL}/entries/${params}`);
  if (!res.ok) {
    throw new Error('Failed to load entries');
  }
  return res.json();
}

export async function getEntry(id: number): Promise<CodexEntryDetail> {
  const res = await apiFetch(`${BASE_URL}/entries/${id}/`);
  if (!res.ok) {
    throw new Error('Failed to load entry');
  }
  return res.json();
}

export async function searchEntries(query: string): Promise<CodexEntryListItem[]> {
  if (query.length < 2) return [];
  const res = await apiFetch(`${BASE_URL}/entries/?search=${encodeURIComponent(query)}`);
  if (!res.ok) {
    throw new Error('Failed to search entries');
  }
  return res.json();
}

export async function getSubjectChildren(subjectId: number): Promise<CodexSubjectTreeNode[]> {
  const res = await apiFetch(`${BASE_URL}/subjects/${subjectId}/children/`);
  if (!res.ok) {
    throw new Error('Failed to load subject children');
  }
  return res.json();
}
