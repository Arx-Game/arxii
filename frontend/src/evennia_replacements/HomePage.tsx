import { Link } from 'react-router-dom';

import { Button } from '../components/ui/button';
import { SITE_NAME } from '../config';
import { StatusBlock } from './StatusBlock';
import { NewPlayerSection } from './NewPlayerSection';
import { LoreTabs } from './LoreTabs';
import { QuickActions } from '../components/QuickActions';
import { ScenesSpotlight } from '../components/ScenesSpotlight';
import { StatsCard } from './StatsCard';
import { RecentConnected } from './RecentConnected';
import { NewsTeaser } from './NewsTeaser';
import { useStatusQuery } from './queries';

export function HomePage() {
  const { data, isLoading } = useStatusQuery();

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
      <div className="container mx-auto grid gap-4 py-8 md:grid-cols-3">
        <StatsCard
          stats={
            data
              ? {
                  accounts: data.accounts,
                  characters: data.characters,
                  rooms: data.rooms,
                }
              : undefined
          }
          isLoading={isLoading}
        />
        <RecentConnected accounts={data?.recentPlayers} isLoading={isLoading} />
        <NewsTeaser news={data?.news} isLoading={isLoading} />
      </div>
      <ScenesSpotlight />
      <QuickActions />
      <NewPlayerSection />
      <LoreTabs />
    </>
  );
}
