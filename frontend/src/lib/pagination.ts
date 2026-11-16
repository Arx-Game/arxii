import { apiFetch } from '@/evennia_replacements/api';
import { readErrorDetail } from '@/lib/errors';

interface Paginated<T> {
  next: string | null;
  results: T[];
}

/** The path and query of a paginator's `next` link, to follow on this page's origin. */
export function sameSitePath(next: string): string {
  const link = new URL(next, window.location.origin);
  return `${link.pathname}${link.search}`;
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
    // DRF builds `next` on the host the API saw, which behind the dev proxy (or a public
    // proxy that rewrites Host) is not the page's own. The link always names our API, so
    // keep its path and query and follow it on this page's origin (#5140).
    url = data.next === null ? null : sameSitePath(data.next);
    pages += 1;
  }
  return all;
}
