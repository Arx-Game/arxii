import { Link } from 'react-router-dom';
import { Avatar, AvatarImage, AvatarFallback } from '../ui/avatar';
import { cn } from '../../lib/utils';

interface CharacterAvatarLinkProps {
  id: number;
  name?: string;
  avatarUrl?: string;
  className?: string;
  fallback?: string;
}

export function CharacterAvatarLink({
  id,
  name,
  avatarUrl,
  className,
  fallback,
}: CharacterAvatarLinkProps) {
  const computed = name?.slice(0, 2).toUpperCase();
  const fallbackText = fallback ?? (computed && computed !== '' ? computed : '??');
  return (
    <Link to={`/characters/${id}`}>
      <Avatar className={cn(className)}>
        {avatarUrl ? <AvatarImage src={avatarUrl} alt={name} /> : null}
        <AvatarFallback>{fallbackText}</AvatarFallback>
      </Avatar>
    </Link>
  );
}
