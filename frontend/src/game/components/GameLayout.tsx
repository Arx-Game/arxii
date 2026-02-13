import type { ReactNode } from 'react';

interface GameLayoutProps {
  topBar: ReactNode;
  leftSidebar: ReactNode;
  center: ReactNode;
  rightSidebar: ReactNode;
}

export function GameLayout({ topBar, leftSidebar, center, rightSidebar }: GameLayoutProps) {
  return (
    <div className="flex h-[calc(100vh-4rem)] flex-col">
      {topBar}
      <div className="grid min-h-0 flex-1 grid-cols-[200px_1fr_280px]">
        <div className="overflow-y-auto border-r bg-card">{leftSidebar}</div>
        <div className="flex min-h-0 flex-col overflow-hidden">{center}</div>
        <div className="overflow-y-auto border-l bg-card">{rightSidebar}</div>
      </div>
    </div>
  );
}
