/**
 * An element drawn through a portal to <body> is outside the page's `.interview` root,
 * so a `.interview <descendant>` rule never reaches it (#5148: the term definition box
 * was right in markup and class names and had no styles at all, from #4874 on). Such an
 * element carries the root class itself beside its own, and its rules name both classes
 * on the one element.
 *
 * This reads the sources: jsdom applies no stylesheet, so a rendered test cannot tell a
 * rule that reaches the element from one that does not.
 */
import { readFileSync } from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';

// Read from disk: vitest hands back an empty string for an imported stylesheet.
const here = path.dirname(fileURLToPath(import.meta.url));
const stylesheet = readFileSync(path.resolve(here, '..', 'cg.css'), 'utf8');

const sources = import.meta.glob('../**/*.tsx', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

/** Every class an element carries beside the root class: `className="interview popover"`. */
function classesBesideTheRoot(): { file: string; name: string }[] {
  const found: { file: string; name: string }[] = [];
  for (const [file, text] of Object.entries(sources)) {
    if (file.includes('__tests__')) continue;
    for (const match of text.matchAll(/className="interview ([^"]+)"/g)) {
      for (const name of match[1].split(/\s+/).filter(Boolean)) found.push({ file, name });
    }
  }
  return found;
}

describe('an element that carries the root class itself', () => {
  const carried = classesBesideTheRoot();

  it('is found (the term definition box, at least)', () => {
    expect(carried.map((c) => c.name)).toContain('popover');
  });

  it.each(carried)('$name has a rule naming both classes on the one element', ({ name }) => {
    expect(stylesheet).toMatch(new RegExp(`\\.interview\\.${name}[\\s{,.:>]`));
  });

  it.each(carried)('$name is styled by no descendant rule, which cannot reach it', ({ name }) => {
    expect(stylesheet).not.toMatch(new RegExp(`\\.interview \\.${name}[\\s{,.:>]`));
  });
});
