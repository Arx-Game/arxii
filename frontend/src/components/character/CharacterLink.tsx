import { forwardRef } from 'react';
import { Link } from 'react-router-dom';
import type { ComponentPropsWithoutRef } from 'react';
import { cn } from '@/lib/utils';
import { urls } from '@/utils/urls';

interface CharacterLinkProps extends Omit<ComponentPropsWithoutRef<typeof Link>, 'to' | 'id'> {
  id: number;
}

// Forwards its ref and props: a menu item rendered `asChild` (the account menu)
// hands the link its role, focus handlers and ref, and drops nothing on the way.
export const CharacterLink = forwardRef<HTMLAnchorElement, CharacterLinkProps>(
  ({ id, className, ...props }, ref) => (
    <Link ref={ref} to={urls.character(id)} className={cn(className)} {...props} />
  )
);
CharacterLink.displayName = 'CharacterLink';
