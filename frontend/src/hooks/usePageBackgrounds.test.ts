import { describe, expect, it } from 'vitest';
import { pageBackgroundStyle } from './usePageBackgrounds';

describe('pageBackgroundStyle', () => {
  it('returns a cover backgroundImage when art_url is set for the slot', () => {
    const style = pageBackgroundStyle(
      [{ slot: 'homepage', art_url: 'https://example.com/hero.jpg' }],
      'homepage',
      'Homepage'
    );
    expect(style.backgroundImage).toBe('url(https://example.com/hero.jpg)');
    expect(style.backgroundSize).toBe('cover');
  });

  it('falls back to a gradient when no art is set for the slot', () => {
    const style = pageBackgroundStyle(
      [{ slot: 'homepage', art_url: null }],
      'homepage',
      'Homepage'
    );
    expect(style.background).toMatch(/^linear-gradient/);
  });

  it('falls back to a gradient when backgrounds have not loaded yet', () => {
    const style = pageBackgroundStyle(undefined, 'homepage', 'Homepage');
    expect(style.background).toMatch(/^linear-gradient/);
  });
});
