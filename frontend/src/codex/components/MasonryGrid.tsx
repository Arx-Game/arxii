import Masonry from 'react-masonry-css';
import type { ReactNode } from 'react';

interface MasonryGridProps {
  children: ReactNode;
}

const breakpointColumns = {
  default: 3,
  1100: 2,
  700: 1,
};

export function MasonryGrid({ children }: MasonryGridProps) {
  return (
    <Masonry
      breakpointCols={breakpointColumns}
      className="-ml-4 flex w-auto"
      columnClassName="pl-4 bg-clip-padding"
    >
      {children}
    </Masonry>
  );
}
