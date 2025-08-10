import { Link } from 'react-router-dom';

import { Button } from '../components/ui/button';
import { SITE_NAME } from '../config';
import { StatusBlock } from './StatusBlock';
import { NewPlayerSection } from './NewPlayerSection';
import { QuickActions } from '../components/QuickActions';

export function HomePage() {
  return (
    <>
      <section
        id="hero"
        className="container mx-auto flex flex-col items-center gap-8 py-12 text-center"
      >
        <div className="flex flex-col items-center gap-2">
          <h1 className="text-4xl font-bold tracking-tight">Welcome to {SITE_NAME}!</h1>
          <p className="text-lg text-muted-foreground">The Python MUD/MU* creation system.</p>
        </div>
        <Button asChild size="lg">
          <Link to="/game">Play in the browser</Link>
        </Button>
        <StatusBlock />
      </section>
      <QuickActions />
      <NewPlayerSection />
    </>
  );
}
