import type { SocialConsentCategory } from './types';

export interface FlatTreeNode {
  category: SocialConsentCategory;
  depth: number;
}

/**
 * Flatten the consent-category tree into pre-order display rows (#2170).
 *
 * Roots (`parent == null`) come first, each immediately followed by its descendants, so a
 * caller can render the tree as an indented list keyed off `depth`. Ordering within a level
 * is by `display_order` then `name`. Cycle- and orphan-guarded: a node whose `parent` is not
 * present in the list is treated as a root, and a mis-seeded loop cannot recurse forever.
 */
export function flattenCategoryTree(categories: SocialConsentCategory[]): FlatTreeNode[] {
  const byParent = new Map<number | null, SocialConsentCategory[]>();
  const ids = new Set(categories.map((c) => c.id));
  for (const category of categories) {
    // An unknown parent id (not in this list) is displayed as a root.
    const key = category.parent != null && ids.has(category.parent) ? category.parent : null;
    const bucket = byParent.get(key) ?? [];
    bucket.push(category);
    byParent.set(key, bucket);
  }
  for (const bucket of byParent.values()) {
    bucket.sort((a, b) => a.display_order - b.display_order || a.name.localeCompare(b.name));
  }

  const rows: FlatTreeNode[] = [];
  const seen = new Set<number>();
  const visit = (category: SocialConsentCategory, depth: number): void => {
    if (seen.has(category.id)) {
      return;
    }
    seen.add(category.id);
    rows.push({ category, depth });
    for (const child of byParent.get(category.id) ?? []) {
      visit(child, depth + 1);
    }
  };
  for (const root of byParent.get(null) ?? []) {
    visit(root, 0);
  }
  // Safety net: a category unreachable from any root (a pure parent cycle) must still render
  // rather than silently vanish — emit any unvisited node as a fallback root, in input order.
  for (const category of categories) {
    if (!seen.has(category.id)) {
      visit(category, 0);
    }
  }
  return rows;
}
