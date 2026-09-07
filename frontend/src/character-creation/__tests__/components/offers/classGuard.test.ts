/**
 * classGuard.ts unit test (#3675 fix round 1): `unreachableClasses` is shared
 * by ChapterOffers.test.tsx and UpbringingPrompts.test.tsx and must never
 * throw on a shadcn/Tailwind class name that contains a `:`
 * (`peer-disabled:cursor-not-allowed` and similar) - a valid class-list
 * token, but an invalid bare CSS selector for `querySelectorAll('.name')`.
 */
import { unreachableClasses } from './classGuard';

describe('unreachableClasses', () => {
  it('does not throw on a colon-bearing class name', () => {
    const container = document.createElement('div');
    const child = document.createElement('span');
    child.className = 'peer-disabled:cursor-not-allowed';
    container.appendChild(child);
    expect(() => unreachableClasses(container)).not.toThrow();
  });
});
