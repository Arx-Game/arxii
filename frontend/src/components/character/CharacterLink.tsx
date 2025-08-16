import { Link } from 'react-router-dom';
import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';
import { urls } from '@/utils/urls';

interface CharacterLinkProps {
  id: number;
  children: ReactNode;
  className?: string;
}

export function CharacterLink({ id, children, className }: CharacterLinkProps) {
  return (
    <Link to={urls.character(id)} className={cn(className)}>
      {children}
    </Link>
  );
}
