import { Link } from 'react-router-dom';
import { useLogout, useMyRosterEntriesQuery } from '../evennia_replacements/queries';
import type { AccountData } from '../evennia_replacements/types';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from './ui/dropdown-menu';

interface ProfileDropdownProps {
  account: AccountData;
}

export function ProfileDropdown({ account }: ProfileDropdownProps) {
  const logout = useLogout();
  const { data: characters } = useMyRosterEntriesQuery(true);

  return (
    <DropdownMenu>
      <DropdownMenuTrigger className="font-medium">{account.display_name}</DropdownMenuTrigger>
      <DropdownMenuContent>
        {characters?.map((c) => (
          <DropdownMenuItem key={c.id} asChild>
            <Link to={`/characters/${c.id}`}>{c.name}</Link>
          </DropdownMenuItem>
        ))}
        <DropdownMenuItem asChild>
          <Link to="/profile">Profile</Link>
        </DropdownMenuItem>
        <DropdownMenuItem onClick={() => logout.mutate()}>Logout</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
