import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useLogout, useMyRosterEntriesQuery } from '../evennia_replacements/queries';
import type { AccountData } from '../evennia_replacements/types';

interface ProfileDropdownProps {
  account: AccountData;
}

export function ProfileDropdown({ account }: ProfileDropdownProps) {
  const [open, setOpen] = useState(false);
  const logout = useLogout(() => setOpen(false));
  const { data: characters } = useMyRosterEntriesQuery(true);

  return (
    <div className="relative">
      <button onClick={() => setOpen(!open)} className="font-medium">
        {account.display_name}
      </button>
      {open && (
        <nav className="absolute right-0 mt-2 w-40 rounded border bg-background shadow-md">
          <ul className="flex flex-col">
            {characters?.map((c) => (
              <li key={c.id}>
                <Link
                  to={`/characters/${c.id}`}
                  className="block px-4 py-2 hover:bg-accent hover:text-accent-foreground"
                  onClick={() => setOpen(false)}
                >
                  {c.name}
                </Link>
              </li>
            ))}
            <li>
              <Link
                to="/profile"
                className="block px-4 py-2 hover:bg-accent hover:text-accent-foreground"
                onClick={() => setOpen(false)}
              >
                Profile
              </Link>
            </li>
            <li>
              <button
                onClick={() => logout.mutate()}
                className="block w-full px-4 py-2 text-left hover:bg-accent hover:text-accent-foreground"
              >
                Logout
              </button>
            </li>
          </ul>
        </nav>
      )}
    </div>
  );
}
