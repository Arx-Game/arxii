import { Link } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { WelcomePanel } from '@/components/WelcomePanel';
import { SITE_NAME } from '@/config';
import { StatusBlock } from './StatusBlock';
import { NewPlayerSection } from './NewPlayerSection';
import { FeaturedLore } from './FeaturedLore';
import { QuickActions } from '@/components/QuickActions';
import { ScenesSpotlight } from '@/components/ScenesSpotlight';
import { StatsCard } from './StatsCard';
import { RecentConnected } from './RecentConnected';
import { NewsTeaser } from './NewsTeaser';
import { useStatusQuery } from './queries';
import { useAccount } from '@/store/hooks';
import { usePageBackgrounds, pageBackgroundStyle } from '@/hooks/usePageBackgrounds';

export function HomePage() {
  const { data: backgrounds } = usePageBackgrounds();
  const { data, isLoading } = useStatusQuery();
  const account = useAccount();
  const hasCharacters = (account?.available_characters?.length ?? 0) > 0;
  const heroDestination = account && !hasCharacters ? '/characters/create' : '/game';
  const heroLabel = account && !hasCharacters ? 'Create a character' : 'Play in the browser';

  return (
    <div style={pageBackgroundStyle(backgrounds, 'homepage', 'Homepage')}>
      <section
        id="hero"
        className="container mx-auto flex flex-col items-center gap-8 py-12 text-center"
      >
        <div className="flex flex-col items-center gap-2">
          <h1 className="text-4xl font-bold tracking-tight">Welcome to {SITE_NAME}</h1>
          <p className="text-lg text-muted-foreground">
            A living world of intrigue and magic, played with others in your browser.
          </p>
        </div>
        <Button asChild size="lg">
          <Link to={heroDestination}>{heroLabel}</Link>
        </Button>
        <StatusBlock />
      </section>
      <WelcomePanel />
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
        <RecentConnected entries={data?.recentPlayers} isLoading={isLoading} />
        <NewsTeaser news={data?.news} isLoading={isLoading} />
      </div>
      <ScenesSpotlight />
      <QuickActions />
      <NewPlayerSection />
      <FeaturedLore />
    </div>
  );
}
