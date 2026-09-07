/**
 * The class-hook guard for the `offers/` components (#3675 review round 1),
 * checking reachability rather than mere name presence (#3667 shape): a
 * class hook a component emits must be the rightmost compound of at least
 * one selector in `cg.css` that actually *matches* the rendered element,
 * not just a class name string that happens to appear somewhere in the
 * file. `container` must include an `.interview` ancestor (wrap the render
 * in `<div className="interview">`) so `.interview`-scoped selectors can
 * match through their real ancestor chain.
 *
 * Elements-per-class are found with `classList.contains`, never by building
 * a `.{name}` selector string for `querySelectorAll` (#3675 fix round 1): a
 * shadcn/Tailwind class name can contain a `:` (`peer-disabled:opacity-70`),
 * which is a valid single class-list token but an invalid CSS selector on
 * its own and throws `SyntaxError` from `querySelectorAll`.
 */

/// <reference types="node" />
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

/** Escapes a string for literal use inside a `RegExp` (#3675 fix round 3): a
 * class name can carry regex-special characters (`px-2.5`'s `.`), which would
 * otherwise match as "any character" instead of a literal dot, loosening the
 * candidate-selector match. Exported for its own unit test. */
export function escapeRegExp(value: string): string {
  return value.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/** Selector list per top-level rule header in cg.css (skips @-rule preludes). */
function ruleSelectors(css: string): string[] {
  const stripped = css.replace(/\/\*[\s\S]*?\*\//g, '');
  const selectors: string[] = [];
  const headerRe = /(?:^|\})\s*([^{}]+?)\s*\{/g;
  let match: RegExpExecArray | null;
  while ((match = headerRe.exec(stripped))) {
    const header = match[1].trim();
    if (!header || header.startsWith('@')) continue;
    for (const sel of header.split(',')) {
      const trimmed = sel.trim();
      if (trimmed) selectors.push(trimmed);
    }
  }
  return selectors;
}

/**
 * Every class emitted under `container` that no cg.css selector actually
 * reaches. `styledElsewhere` names classes styled by a different sheet
 * (app-wide utilities), the same escape hatch the FinalTouchesStage guard uses.
 */
export function unreachableClasses(
  container: HTMLElement,
  styledElsewhere: Set<string> = new Set()
): string[] {
  const css = readFileSync(resolve(__dirname, '../../../cg.css'), 'utf8');
  const selectors = ruleSelectors(css);

  const allElements = Array.from(container.querySelectorAll('[class]'));
  const emitted = new Set<string>();
  allElements.forEach((el) => {
    el.className
      .split(/\s+/)
      .filter(Boolean)
      .forEach((name) => emitted.add(name));
  });

  const unreached: string[] = [];
  for (const name of emitted) {
    if (styledElsewhere.has(name)) continue;
    const candidates = selectors.filter((sel) =>
      new RegExp(`\\.${escapeRegExp(name)}(?![\\w-])`).test(sel)
    );
    const elements = allElements.filter((el) => el.classList.contains(name));
    const reached = candidates.some((sel) =>
      elements.some((el) => {
        try {
          return el.matches(sel);
        } catch {
          return false;
        }
      })
    );
    if (!reached) unreached.push(name);
  }
  return unreached;
}
