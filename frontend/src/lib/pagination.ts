import { apiFetch } from '@/evennia_replacements/api';
import { readErrorDetail } from '@/lib/errors';

interface Paginated<T> {
  next: string | null;
  results: T[];
}

/** Backstop against a paginator whose `next` never terminates. */
const MAX_PAGES = 40;

/**
 * Fetch every page of a DRF-paginated list endpoint, following `next` links
 * (2026-07 audit). For "load the whole collection" callers — inventories,
 * journals, pickers — that previously read only `results` of page 1 and
 * silently truncated at the server page size (e.g. a >50-item inventory lost
 * worn items past page 1, turning Wear/Drop buttons into no-ops).
 *
 * Not a replacement for real pagination UI on unbounded lists — use this only
 * where the full set is genuinely needed and plausibly bounded.
 */
export async function fetchAllPages<T>(firstUrl: string, errorMessage: string): Promise<T[]> {
  const all: T[] = [];
  let url: string | null = firstUrl;
  let pages = 0;
  while (url !== null && pages < MAX_PAGES) {
    const res = await apiFetch(url);
    if (!res.ok) {
      await readErrorDetail(res, errorMessage);
    }
    const data = (await res.json()) as Paginated<T>;
    all.push(...data.results);
    // `next` is absolute from DRF; pass through as-is (same-origin).
    url = data.next;
    pages += 1;
  }
  return all;
}
