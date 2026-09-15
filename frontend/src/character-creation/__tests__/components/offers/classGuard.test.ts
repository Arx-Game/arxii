/**
 * classGuard.ts unit test (#3675 fix round 1): `unreachableClasses` is shared
 * by ChapterOffers.test.tsx and UpbringingPrompts.test.tsx and must never
 * throw on a shadcn/Tailwind class name that contains a `:`
 * (`peer-disabled:cursor-not-allowed` and similar) - a valid class-list
 * token, but an invalid bare CSS selector for `querySelectorAll('.name')`.
 */
import { escapeRegExp, unreachableClasses } from './classGuard';

describe('unreachableClasses', () => {
  it('does not throw on a colon-bearing class name', () => {
    const container = document.createElement('div');
    const child = document.createElement('span');
    child.className = 'peer-disabled:cursor-not-allowed';
    container.appendChild(child);
    expect(() => unreachableClasses(container)).not.toThrow();
  });

  it('does not throw on a dotted class name', () => {
    const container = document.createElement('div');
    const child = document.createElement('span');
    child.className = 'px-2.5';
    container.appendChild(child);
    expect(() => unreachableClasses(container)).not.toThrow();
  });

  it('escapes a dot literally instead of leaving it as a regex wildcard', () => {
    expect(escapeRegExp('px-2.5')).toBe('px-2\\.5');
    expect(new RegExp(`^${escapeRegExp('px-2.5')}$`).test('px-2x5')).toBe(false);
  });
});
