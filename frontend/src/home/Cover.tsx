/**
 * Cover — the Gatefold's night-cover hero (#3305).
 *
 * Always rendered against night literals (never theme tokens): a real
 * background-art photo when staff have set one for the `homepage` slot, else
 * the reference's three-layer radial-gradient night (`.gatefold-cover` in
 * home.css). The night look stays constant across light/dark mode — Arx's
 * night sky doesn't change because a visitor prefers a light UI.
 */

import { usePageBackgrounds, pageBackgroundStyle } from '@/hooks/usePageBackgrounds';
import { useMonthlySceneCount } from './queries';

export function Cover() {
  const { data: backgrounds } = usePageBackgrounds();
  const { data: monthlySceneCount } = useMonthlySceneCount();

  const hasArt = backgrounds?.some((b) => b.slot === 'homepage' && b.art_url);
  const coverStyle = hasArt ? pageBackgroundStyle(backgrounds, 'homepage', 'Homepage') : undefined;

  return (
    <section
      className="gatefold-cover min-h-[88svh] dark:border-b dark:border-[rgba(201,168,62,0.25)]"
      style={coverStyle}
    >
      <div className="gatefold-cover-inner">
        <h1 className="font-display">ARX</h1>
        {/* Apostate's prose, verbatim (#3723). */}
        <p className="gatefold-hero-prose">
          For a thousand years, the Shroud sealed the great Necropolis, protecting the city as the
          world was shattered. <em>Now the Shroud has fallen, and no one knows why.</em>
        </p>
        {/* Live count, not copy — computed from useMonthlySceneCount(); hidden when 0/undefined. */}
        {!!monthlySceneCount && (
          <p className="gatefold-hero-plays">
            {monthlySceneCount} public {monthlySceneCount === 1 ? 'scene' : 'scenes'} concluded this
            month
          </p>
        )}
      </div>
    </section>
  );
}
