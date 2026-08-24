import { Link } from 'react-router-dom';
import { Separator } from './ui/separator';

export function Footer() {
  return (
    <footer className="mt-8">
      <Separator />
      <div className="container flex flex-col items-center gap-2 py-6 text-center text-sm text-muted-foreground">
        <nav aria-label="Footer" className="flex items-baseline gap-6">
          <Link to="/codex" className="px-1 py-2 hover:text-foreground hover:underline">
            Codex
          </Link>
          <Link to="/roster" className="px-1 py-2 hover:text-foreground hover:underline">
            Roster
          </Link>
          <Link to="/scenes" className="px-1 py-2 hover:text-foreground hover:underline">
            Scenes
          </Link>
          <Link to="/login" className="px-1 py-2 hover:text-foreground hover:underline">
            Log in
          </Link>
        </nav>
        <p>
          Powered by{' '}
          <a href="https://www.evennia.com" target="_blank" rel="noreferrer" className="underline">
            Evennia
          </a>
        </p>
      </div>
    </footer>
  );
}
