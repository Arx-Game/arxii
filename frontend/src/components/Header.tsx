import { useState } from 'react'
import { Link } from 'react-router-dom'
import { useAccount } from '../store/hooks'
import { useLogout } from '../evennia_replacements/queries'
import { SITE_NAME } from '../config'

export function Header() {
  const account = useAccount()
  const [open, setOpen] = useState(false)
  const logout = useLogout(() => setOpen(false))

  return (
    <header className="border-b">
      <div className="container mx-auto flex items-center justify-between px-4 py-4">
        <h1 className="text-2xl font-bold">
          <Link to="/">{SITE_NAME}</Link>
        </h1>
        {account ? (
          <div className="relative">
            <button
              onClick={() => setOpen(!open)}
              className="font-medium"
            >
              {account.display_name}
            </button>
            {open && (
              <nav className="absolute right-0 mt-2 w-40 rounded border bg-background shadow-md">
                <ul className="flex flex-col">
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
        ) : (
          <nav>
            <Link to="/login" className="text-primary hover:underline">
              Log in
            </Link>
          </nav>
        )}
      </div>
    </header>
  )
}
