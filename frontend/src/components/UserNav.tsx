import { Link } from 'react-router-dom';
import { useAccount } from '../store/hooks';
import { ProfileDropdown } from './ProfileDropdown';

export function UserNav() {
  const account = useAccount();
  if (account) {
    return <ProfileDropdown account={account} />;
  }
  return (
    <nav>
      <Link to="/login" className="text-primary hover:underline">
        Log in
      </Link>
    </nav>
  );
}
