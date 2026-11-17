import { mkdirSync, mkdtempSync, rmSync, writeFileSync } from 'node:fs';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { afterEach, describe, expect, it } from 'vitest';

import { checkBuiltUrls, findRootAnchoredReferences } from './check-built-urls.mjs';

const made = [];

function buildOf(files) {
  const dist = mkdtempSync(join(tmpdir(), 'built-urls-'));
  made.push(dist);
  mkdirSync(join(dist, 'assets'));
  for (const [name, text] of Object.entries(files)) {
    writeFileSync(join(dist, 'assets', name), text);
  }
  return dist;
}

afterEach(() => {
  while (made.length > 0) rmSync(made.pop(), { recursive: true, force: true });
});

describe('check-built-urls', () => {
  it('reports a lazy page stylesheet named from the site root', () => {
    // The shape the default absolute base produced: the preload list holds
    // `assets/<file>` and the helper puts `/` in front of it.
    const dist = buildOf({
      'index-abc.js': 'load(()=>import("./FamilyPage-def.js"),["assets/FamilyPage-ghi.css"])',
      'FamilyPage-def.js': 'export const page = 1;',
      'FamilyPage-ghi.css': '.family{color:red}',
    });

    expect(findRootAnchoredReferences(dist)).toEqual([
      { file: 'assets/index-abc.js', reference: 'assets/FamilyPage-ghi.css' },
    ]);
    expect(() => checkBuiltUrls(dist)).toThrow(/assets\/FamilyPage-ghi\.css/);
  });

  it('reports a stylesheet url() that starts at the site root', () => {
    const dist = buildOf({
      'index-abc.css': '.crest{background:url(/assets/crest-xyz.png)}',
      'crest-xyz.png': '',
    });

    expect(findRootAnchoredReferences(dist)).toEqual([
      { file: 'assets/index-abc.css', reference: '/assets/crest-xyz.png' },
    ]);
  });

  it('passes a build whose files name each other relatively', () => {
    const dist = buildOf({
      'index-abc.js':
        'load(()=>import("./FamilyPage-def.js"),["./FamilyPage-ghi.css"]);fetch("/api/assets/")',
      'FamilyPage-def.js': 'export const page = 1;',
      'FamilyPage-ghi.css': '.crest{background:url(./crest-xyz.png)}',
      'crest-xyz.png': '',
      // A source map repeats the source text and is never requested by a page.
      'index-abc.js.map': '"assets/FamilyPage-ghi.css"',
    });

    expect(findRootAnchoredReferences(dist)).toEqual([]);
    expect(() => checkBuiltUrls(dist)).not.toThrow();
  });
});
