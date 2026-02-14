import { ReactNode } from 'react';
import { useLocation } from 'react-router-dom';
import { Header } from './Header';
import { Footer } from './Footer';

interface LayoutProps {
  children: ReactNode;
}

/** Routes that use a full-viewport layout without container padding or footer. */
const FULL_VIEWPORT_ROUTES = ['/game'];

export function Layout({ children }: LayoutProps) {
  const location = useLocation();
  const isFullViewport = FULL_VIEWPORT_ROUTES.includes(location.pathname);

  return (
    <div
      className={`bg-background ${isFullViewport ? 'flex h-screen flex-col overflow-hidden' : 'min-h-screen'}`}
    >
      <a href="#main-content" className="sr-only focus:not-sr-only">
        Skip to content
      </a>
      <Header />
      {isFullViewport ? (
        <main id="main-content" className="flex min-h-0 flex-1 flex-col">
          {children}
        </main>
      ) : (
        <>
          <main id="main-content" className="container mx-auto px-4 py-8">
            {children}
          </main>
          <Footer />
        </>
      )}
    </div>
  );
}
