/**
 * The class-hook guard for the `offers/` components (#3675 review round 1),
 * checking reachability rather than mere name presence (#3667 shape): a
 * class hook a component emits must be the rightmost compound of at least
 * one selector in `cg.css` that actually *matches* the rendered element,
 * not just a class name string that happens to appear somewhere in the
 * file. `container` must include an `.interview` ancestor (wrap the render
 * in `<div className="interview">`) so `.interview`-scoped selectors can
 * match through their real ancestor chain.
 */

/// <reference types="node" />
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

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

  const emitted = new Set<string>();
  container.querySelectorAll('[class]').forEach((el) => {
    el.className
      .split(/\s+/)
      .filter(Boolean)
      .forEach((name) => emitted.add(name));
  });

  const unreached: string[] = [];
  for (const name of emitted) {
    if (styledElsewhere.has(name)) continue;
    const candidates = selectors.filter((sel) => new RegExp(`\\.${name}(?![\\w-])`).test(sel));
    const elements = Array.from(container.querySelectorAll(`.${name}`));
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
