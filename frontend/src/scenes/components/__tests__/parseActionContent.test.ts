import { describe, it, expect } from 'vitest';

import { parseActionContent } from '../ActionResult';

describe('parseActionContent', () => {
  it('parses the full documented format', () => {
    expect(parseActionContent('[strike] using Cleave -- Success (Wounded)')).toMatchObject({
      actionName: 'strike',
      techniqueName: 'Cleave',
      outcomeName: 'Success',
      consequenceLabel: 'Wounded',
    });
  });

  it('parses each clause as optional', () => {
    expect(parseActionContent('[strike] using Cleave')).toMatchObject({
      actionName: 'strike',
      techniqueName: 'Cleave',
      outcomeName: null,
      consequenceLabel: null,
    });
    expect(parseActionContent('[strike] -- Failure')).toMatchObject({
      actionName: 'strike',
      techniqueName: null,
      outcomeName: 'Failure',
    });
    expect(parseActionContent('[strike]')).toMatchObject({
      actionName: 'strike',
      techniqueName: null,
      outcomeName: null,
    });
  });

  it('falls back when there is no bracketed action key', () => {
    expect(parseActionContent('no brackets')).toMatchObject({
      actionName: 'Action',
      rawContent: 'no brackets',
    });
  });

  // The pattern this replaced swallowed a dangling separator into the technique
  // name and dropped the action key outright when the tail was degenerate.
  it('does not swallow a dangling separator into the technique name', () => {
    expect(parseActionContent('[x] using T --')).toMatchObject({
      actionName: 'x',
      techniqueName: 'T',
      outcomeName: null,
    });
  });

  it('keeps the action key when the tail is degenerate', () => {
    expect(parseActionContent('[x] --')).toMatchObject({ actionName: 'x', outcomeName: null });
    expect(parseActionContent('[x] ()')).toMatchObject({ actionName: 'x' });
  });
});
