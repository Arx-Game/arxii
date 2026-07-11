import { describe, it, expect } from 'vitest';
import { flattenCategoryTree } from '../categoryTree';
import { resolveEffectiveMode } from '../consentModes';
import type { SocialConsentCategory, SocialConsentCategoryRule } from '../types';

function cat(
  id: number,
  name: string,
  parent: number | null,
  default_mode: string,
  display_order = id
): SocialConsentCategory {
  return {
    id,
    key: name.toLowerCase(),
    name,
    description: '',
    display_order,
    parent,
    default_mode,
    action_templates: [],
  } as unknown as SocialConsentCategory;
}

function rule(category: number, mode: string): SocialConsentCategoryRule {
  return {
    id: category * 100,
    preference: 1,
    category,
    mode,
  } as unknown as SocialConsentCategoryRule;
}

// Root "All Antagonism" (friends_whitelist) with two leaves; plus a standalone "Romantic" root.
const antagonism = cat(1, 'All Antagonism', null, 'friends_whitelist', 5);
const hostile = cat(2, 'Hostile', 1, 'everyone', 20);
const blackmail = cat(3, 'Blackmail', 1, 'friends_whitelist', 25);
const romantic = cat(4, 'Romantic', null, 'everyone', 10);
const all = [hostile, romantic, antagonism, blackmail];

describe('flattenCategoryTree', () => {
  it('orders roots by display_order, each followed by its children', () => {
    const rows = flattenCategoryTree(all).map((r) => [r.category.name, r.depth]);
    expect(rows).toEqual([
      ['All Antagonism', 0],
      ['Hostile', 1],
      ['Blackmail', 1],
      ['Romantic', 0],
    ]);
  });

  it('treats an unknown parent id as a root and does not loop on a cycle', () => {
    const a = cat(1, 'A', 2, 'everyone');
    const b = cat(2, 'B', 1, 'everyone');
    const orphan = cat(3, 'Orphan', 99, 'everyone');
    const rows = flattenCategoryTree([a, b, orphan]);
    // Every node appears exactly once despite the A<->B cycle + orphan's missing parent.
    expect(rows.map((r) => r.category.id).sort()).toEqual([1, 2, 3]);
  });
});

describe('resolveEffectiveMode', () => {
  const byId = new Map(all.map((c) => [c.id, c]));

  it('inherits the root default when a leaf has no rule', () => {
    expect(resolveEffectiveMode(hostile.id, byId, new Map())).toBe('friends_whitelist');
  });

  it("uses a leaf's own rule over the inherited default", () => {
    const rules = new Map([[hostile.id, rule(hostile.id, 'everyone')]]);
    expect(resolveEffectiveMode(hostile.id, byId, rules)).toBe('everyone');
  });

  it('inherits a rule set on an ancestor', () => {
    const rules = new Map([[antagonism.id, rule(antagonism.id, 'rivals')]]);
    expect(resolveEffectiveMode(blackmail.id, byId, rules)).toBe('rivals');
  });

  it('falls back to a root category own default_mode', () => {
    expect(resolveEffectiveMode(romantic.id, byId, new Map())).toBe('everyone');
  });
});
