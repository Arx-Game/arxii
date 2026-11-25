/**
 * An element drawn through a portal to <body> is outside the page's `.interview` root,
 * so a `.interview <descendant>` rule never reaches it (#5148: the term definition box
 * was right in markup and class names and had no styles at all, from #4874 on). Such an
 * element carries the root class itself beside its own, and its rules name both classes
 * on the one element.
 *
 * The character sheet's root, `.refsheet`, has the same shape (#5206): the Bonuses band's
 * term definition box is portaled too, carries `refsheet` itself and is styled in
 * `character_sheets/sheet.css` by a rule naming both classes. The shared box lives in
 * `components/term/DefinedTerm.tsx`, which both pages render.
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
const stylesheets: Record<string, string> = {
  interview: readFileSync(path.resolve(here, '..', 'cg.css'), 'utf8'),
  // The sheet's stylesheet and the Gallery's, whose dialogs (also portaled) are styled by
  // their own top-level class rules rather than through the root.
  refsheet: ['sheet.css', 'components/sheet/gallery/gallery.css']
    .map((file) => readFileSync(path.resolve(here, '..', '..', 'character_sheets', file), 'utf8'))
    .join('\n'),
};

/** A rule that reaches a portaled element: both classes on the one element
 * (`.interview.popover`); on the sheet a top-level rule for the class alone reaches it too
 * (the Gallery's `.gallery-dialog`), since the sheet's stylesheets are not all scoped. */
function reaching(root: string, name: string): RegExp {
  if (root === 'interview') return new RegExp(`\\.interview\\.${name}[\\s{,.:>]`);
  return new RegExp(`(?<!\\.refsheet )\\.${name}[\\s{,.:>]`);
}

const sources = {
  ...import.meta.glob('../**/*.tsx', { query: '?raw', import: 'default', eager: true }),
  ...import.meta.glob('../../character_sheets/**/*.tsx', {
    query: '?raw',
    import: 'default',
    eager: true,
  }),
  ...import.meta.glob('../../components/term/*.tsx', {
    query: '?raw',
    import: 'default',
    eager: true,
  }),
} as Record<string, string>;

/** Every class an element carries beside a root class: `className="interview popover"`. */
function classesBesideTheRoot(root: string): { file: string; name: string }[] {
  const found: { file: string; name: string }[] = [];
  const pattern = new RegExp(`className="${root} ([^"]+)"`, 'g');
  for (const [file, text] of Object.entries(sources)) {
    if (file.includes('__tests__')) continue;
    for (const match of text.matchAll(pattern)) {
      for (const name of match[1].split(/\s+/).filter(Boolean)) found.push({ file, name });
    }
  }
  return found;
}

describe.each(['interview', 'refsheet'])('an element that carries .%s itself', (root) => {
  const carried = classesBesideTheRoot(root);
  const stylesheet = stylesheets[root];

  it('is found (the term definition box, at least)', () => {
    expect(carried.map((c) => c.name)).toContain('popover');
  });

  it.each(carried)('$name has a rule that reaches it outside the root', ({ name }) => {
    expect(stylesheet).toMatch(reaching(root, name));
  });

  it.each(carried)('$name is styled by no descendant rule, which cannot reach it', ({ name }) => {
    expect(stylesheet).not.toMatch(new RegExp(`\\.${root} \\.${name}[\\s{,.:>]`));
  });
});
