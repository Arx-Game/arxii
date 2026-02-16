/**
 * ThemeBackground — renders a subtle CSS-only texture layer behind page
 * content. Each realm theme gets a distinct ambient texture.
 */

import { useRealmTheme, type RealmTheme } from './realm-theme-provider';

/** CSS background patterns per realm. All CSS-only, no images. */
const REALM_TEXTURES: Record<RealmTheme, string> = {
  default: `
    radial-gradient(circle at 20% 50%, hsl(35 30% 90% / 0.5) 0%, transparent 50%),
    radial-gradient(circle at 80% 20%, hsl(38 40% 85% / 0.4) 0%, transparent 40%)
  `,
  arx: `
    radial-gradient(circle at 30% 70%, hsl(43 25% 75% / 0.25) 0%, transparent 50%),
    radial-gradient(circle at 70% 30%, hsl(220 12% 65% / 0.18) 0%, transparent 50%),
    repeating-linear-gradient(
      90deg,
      transparent 0px,
      transparent 60px,
      hsl(40 12% 50% / 0.04) 60px,
      hsl(40 12% 50% / 0.04) 61px
    )
  `,
  umbros: `
    radial-gradient(ellipse at 50% 0%, hsl(215 18% 18% / 0.14) 0%, transparent 60%),
    radial-gradient(circle at 80% 80%, hsl(340 18% 22% / 0.1) 0%, transparent 40%)
  `,
  luxen: `
    radial-gradient(circle at 50% 30%, hsl(42 55% 75% / 0.25) 0%, transparent 50%),
    radial-gradient(circle at 20% 80%, hsl(42 45% 80% / 0.14) 0%, transparent 40%)
  `,
  inferna: `
    radial-gradient(circle at 60% 80%, hsl(18 45% 38% / 0.14) 0%, transparent 50%),
    radial-gradient(circle at 30% 20%, hsl(25 55% 48% / 0.1) 0%, transparent 40%)
  `,
  ariwn: `
    radial-gradient(circle at 40% 60%, hsl(350 25% 22% / 0.14) 0%, transparent 50%),
    radial-gradient(circle at 70% 20%, hsl(38 30% 32% / 0.1) 0%, transparent 40%)
  `,
  aythirmok: `
    radial-gradient(circle at 50% 50%, hsl(205 30% 65% / 0.18) 0%, transparent 60%),
    radial-gradient(circle at 20% 30%, hsl(30 45% 48% / 0.1) 0%, transparent 40%)
  `,
};

export function ThemeBackground() {
  const { realmTheme, plainMode } = useRealmTheme();

  if (!realmTheme || plainMode) return null;

  const texture = REALM_TEXTURES[realmTheme];

  return (
    <div
      className="pointer-events-none fixed inset-0 -z-10 transition-opacity duration-1000"
      style={{ background: texture }}
      aria-hidden="true"
    />
  );
}
