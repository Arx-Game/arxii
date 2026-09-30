/**
 * `AREA_LEVELS` is a hand-written copy of `world.areas.constants.AreaLevel` (#4085).
 * The generated OpenAPI schema carries the enum's values and labels, so the copy is
 * checked against it here rather than trusted: the four feudal rungs of #3983 went
 * missing from the copy for six days before anyone noticed (#4084).
 */
import { readFileSync } from 'node:fs';
import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, expect, it } from 'vitest';
import { AREA_LEVELS } from '../types';

const here = path.dirname(fileURLToPath(import.meta.url));
const SCHEMA = path.resolve(here, '..', '..', '..', '..', 'src', 'schema.json');

/** The `(value, label)` pairs of the enum `WorldBuilderArea.level` refers to. */
function schemaAreaLevels(): { value: number; label: string }[] {
  const text = readFileSync(SCHEMA, 'utf8');
  const area = text.indexOf('\n    WorldBuilderArea:\n');
  expect(area).toBeGreaterThan(-1);
  const levelAt = text.indexOf('\n        level:\n', area);
  const ref = /\$ref: '#\/components\/schemas\/(\w+)'/.exec(text.slice(levelAt, levelAt + 300));
  expect(ref).not.toBeNull();
  const enumAt = text.indexOf(`\n    ${ref![1]}:\n`);
  expect(enumAt).toBeGreaterThan(-1);
  // The block ends at the next top-level schema (four spaces then a name).
  const rest = text.slice(enumAt + 1);
  const next = /\n {4}\S/.exec(rest);
  const block = next ? rest.slice(0, next.index) : rest;
  const pairs: { value: number; label: string }[] = [];
  for (const line of block.split('\n')) {
    const m = /^\s+\* `(\d+)` - (.+)$/.exec(line);
    if (m) pairs.push({ value: Number(m[1]), label: m[2].trim() });
  }
  return pairs;
}

describe('AREA_LEVELS', () => {
  it('matches the AreaLevel enum the API publishes, value for value and label for label', () => {
    const fromSchema = schemaAreaLevels();
    expect(fromSchema.length).toBeGreaterThan(0);
    expect(AREA_LEVELS).toEqual(fromSchema);
  });
});
