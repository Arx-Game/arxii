import { Link } from 'react-router-dom';
import { useLogout } from '@/evennia_replacements/queries';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import type { AccountData } from '@/evennia_replacements/types';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from './ui/dropdown-menu';
import { Avatar, AvatarFallback, AvatarImage } from './ui/avatar';
import { CharacterLink } from './character';
import { PlusCircle } from 'lucide-react';

interface ProfileDropdownProps {
  account: AccountData;
}

export function ProfileDropdown({ account }: ProfileDropdownProps) {
  const logout = useLogout();
  const { data: characters } = useMyRosterEntriesQuery(true);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="flex items-center gap-2 font-medium focus:outline-none">
        <Avatar className="h-8 w-8">
          {account.avatar_url ? (
            <AvatarImage src={account.avatar_url} alt={account.display_name} />
          ) : null}
          <AvatarFallback>{account.display_name.charAt(0)}</AvatarFallback>
        </Avatar>
        {account.display_name}
      </DropdownMenuTrigger>
      <DropdownMenuContent>
        <DropdownMenuLabel>Characters</DropdownMenuLabel>
        {characters?.length ? (
          <>
            {characters.map((c) => (
              <DropdownMenuItem key={c.id} asChild inset>
                <CharacterLink id={c.id}>{c.name}</CharacterLink>
              </DropdownMenuItem>
            ))}
          </>
        ) : (
          <DropdownMenuItem disabled inset>
            <span className="text-sm text-muted-foreground">No characters yet</span>
          </DropdownMenuItem>
        )}
        {account.can_create_characters && (
          <DropdownMenuItem asChild inset>
            <Link to="/characters/create" className="flex items-center gap-2">
              <PlusCircle className="h-4 w-4" />
              Create Character
            </Link>
          </DropdownMenuItem>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/roster">Browse Roster</Link>
        </DropdownMenuItem>
        <DropdownMenuSeparator />
        <DropdownMenuItem asChild>
          <Link to="/profile">Profile</Link>
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => logout.mutate()}>Logout</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
