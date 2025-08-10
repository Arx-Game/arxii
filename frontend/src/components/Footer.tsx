import { Button } from './ui/button';
import { Separator } from './ui/separator';

export function Footer() {
  return (
    <footer className="mt-8">
      <Separator />
      <div className="container flex flex-col items-center gap-2 py-6 text-center text-sm text-muted-foreground">
        <div className="flex gap-4">
          <Button variant="ghost" asChild>
            <a href="/docs">Docs</a>
          </Button>
          <Button variant="ghost" asChild>
            <a href="/policies">Policies</a>
          </Button>
          <Button variant="ghost" asChild>
            <a href="/credits">Credits</a>
          </Button>
        </div>
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
