/**
 * ThemeBackground — renders a subtle CSS-only texture layer behind page
 * content. Each realm theme gets a distinct ambient texture.
 */

import { useRealmTheme, type RealmTheme } from './realm-theme-provider';

/** CSS background patterns per realm. All CSS-only, no images. */
const REALM_TEXTURES: Record<RealmTheme, string> = {
  default: `
    radial-gradient(circle at 20% 50%, hsl(35 30% 90% / 0.4) 0%, transparent 50%),
    radial-gradient(circle at 80% 20%, hsl(38 40% 85% / 0.3) 0%, transparent 40%)
  `,
  arx: `
    radial-gradient(circle at 30% 70%, hsl(43 20% 80% / 0.15) 0%, transparent 50%),
    radial-gradient(circle at 70% 30%, hsl(220 10% 70% / 0.1) 0%, transparent 50%),
    repeating-linear-gradient(
      90deg,
      transparent 0px,
      transparent 60px,
      hsl(40 10% 50% / 0.02) 60px,
      hsl(40 10% 50% / 0.02) 61px
    )
  `,
  umbros: `
    radial-gradient(ellipse at 50% 0%, hsl(215 15% 20% / 0.08) 0%, transparent 60%),
    radial-gradient(circle at 80% 80%, hsl(340 15% 25% / 0.06) 0%, transparent 40%)
  `,
  luxen: `
    radial-gradient(circle at 50% 30%, hsl(42 50% 80% / 0.15) 0%, transparent 50%),
    radial-gradient(circle at 20% 80%, hsl(42 40% 85% / 0.08) 0%, transparent 40%)
  `,
  inferna: `
    radial-gradient(circle at 60% 80%, hsl(18 40% 40% / 0.08) 0%, transparent 50%),
    radial-gradient(circle at 30% 20%, hsl(25 50% 50% / 0.06) 0%, transparent 40%)
  `,
  ariwn: `
    radial-gradient(circle at 40% 60%, hsl(350 20% 25% / 0.08) 0%, transparent 50%),
    radial-gradient(circle at 70% 20%, hsl(38 25% 35% / 0.06) 0%, transparent 40%)
  `,
  aythirmok: `
    radial-gradient(circle at 50% 50%, hsl(205 25% 70% / 0.1) 0%, transparent 60%),
    radial-gradient(circle at 20% 30%, hsl(30 40% 50% / 0.06) 0%, transparent 40%)
  `,
};

export function ThemeBackground() {
  const { realmTheme } = useRealmTheme();

  if (!realmTheme) return null;

  const texture = REALM_TEXTURES[realmTheme];

  return (
    <div
      className="pointer-events-none fixed inset-0 -z-10 transition-opacity duration-1000"
      style={{ background: texture }}
      aria-hidden="true"
    />
  );
}
