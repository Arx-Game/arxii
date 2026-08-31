import { useTheme } from 'next-themes';
import { Button } from './ui/button';
import { Moon, Monitor, Sun } from 'lucide-react';

const THEME_ORDER = ['light', 'dark', 'system'] as const;
type OrderedTheme = (typeof THEME_ORDER)[number];

export function ModeToggle() {
  const { theme, setTheme } = useTheme();
  // next-themes hands back whatever localStorage holds, unvalidated — a stale
  // value from an older deploy is not in THEME_ORDER, which used to render an
  // ICONLESS (but clickable) button whose first click "switched to" light
  // (indexOf -1 + 1 = 0). Treat anything unrecognized as system.
  const current: OrderedTheme = THEME_ORDER.includes(theme as OrderedTheme)
    ? (theme as OrderedTheme)
    : 'system';
  const next = THEME_ORDER[(THEME_ORDER.indexOf(current) + 1) % THEME_ORDER.length];

  return (
    <Button variant="ghost" size="icon" onClick={() => setTheme(next)}>
      {current === 'light' && <Sun className="h-[1.2rem] w-[1.2rem]" />}
      {current === 'dark' && <Moon className="h-[1.2rem] w-[1.2rem]" />}
      {current === 'system' && <Monitor className="h-[1.2rem] w-[1.2rem]" />}
      <span className="sr-only">{`Theme: ${current}. Switch to ${next}.`}</span>
    </Button>
  );
}
