import { ReactNode } from 'react';
import { matchPath, useLocation } from 'react-router-dom';
import { Header } from './Header';
import { Footer } from './Footer';
import { ThemeBackground } from './theme-background';
import { PendingAlterationBanner } from '@/magic/components/alterations/PendingAlterationBanner';
import { SeanceOfferBanner } from '@/ceremonies/SeanceOfferBanner';
import { ConversionOfferBanner } from '@/ceremonies/ConversionOfferBanner';
import { DowntimeBanner } from './DowntimeBanner';

interface LayoutProps {
  children: ReactNode;
}

/** Route patterns that use a full-viewport layout without header, padding or footer. */
const FULL_VIEWPORT_ROUTES: readonly string[] = ['/game', '/staff/world-builder/map/:regionId'];

/** Routes that use a full-bleed layout (no container padding) but keep the Footer (#3305, #3540). */
const FULL_BLEED_ROUTES: ReadonlySet<string> = new Set(['/', '/characters/create']);

export function Layout({ children }: LayoutProps) {
  const location = useLocation();
  const isFullViewport = FULL_VIEWPORT_ROUTES.some((route) => matchPath(route, location.pathname));
  const isFullBleed = FULL_BLEED_ROUTES.has(location.pathname);

  const renderFullViewport = () => {
    if (isFullViewport) {
      return (
        <main id="main-content" className="flex min-h-0 flex-1 flex-col">
          {children}
        </main>
      );
    }
    if (isFullBleed) {
      return (
        <>
          <main id="main-content">{children}</main>
          <Footer />
        </>
      );
    }
    return (
      <>
        <main id="main-content" className="container mx-auto px-4 py-8">
          {children}
        </main>
        <Footer />
      </>
    );
  };

  return (
    <div
      className={`bg-background ${isFullViewport ? 'flex h-screen flex-col overflow-hidden' : 'min-h-screen'}`}
    >
      <ThemeBackground />
      <a href="#main-content" className="sr-only focus:not-sr-only">
        Skip to content
      </a>
      {!isFullViewport && <Header />}
      <DowntimeBanner />
      <PendingAlterationBanner />
      <SeanceOfferBanner />
      <ConversionOfferBanner />
      {renderFullViewport()}
    </div>
  );
}
