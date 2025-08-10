import { ReactNode } from 'react';
import { Header } from './Header';

interface LayoutProps {
  children: ReactNode;
}

export function Layout({ children }: LayoutProps) {
  return (
    <div className="min-h-screen bg-background">
      <a href="#main-content" className="sr-only focus:not-sr-only">
        Skip to content
      </a>
      <Header />
      <main id="main-content" className="container mx-auto px-4 py-8">
        {children}
      </main>
    </div>
  );
}
