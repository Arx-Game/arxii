import { useTheme } from 'next-themes';
import { Button } from './ui/button';
import { Moon, Monitor, Sun } from 'lucide-react';

const THEME_ORDER = ['light', 'dark', 'system'] as const;
type OrderedTheme = (typeof THEME_ORDER)[number];

export function ModeToggle() {
  const { theme, setTheme } = useTheme();
  const current = (theme ?? 'system') as OrderedTheme;
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
