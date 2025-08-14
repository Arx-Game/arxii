import { Link } from 'react-router-dom';
import type { ReactNode } from 'react';
import { cn } from '../../lib/utils';

interface CharacterLinkProps {
  id: number;
  children: ReactNode;
  className?: string;
}

export function CharacterLink({ id, children, className }: CharacterLinkProps) {
  return (
    <Link to={`/characters/${id}`} className={cn(className)}>
      {children}
    </Link>
  );
}
