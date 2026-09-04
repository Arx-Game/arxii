import { ConnectedAccounts } from '@/components/ConnectedAccounts';
import { EmailCard } from '../components/EmailCard';
import { PasswordCard } from '../components/PasswordCard';
import { TwoFactorCard } from '../components/TwoFactorCard';

/** /profile/account (#3591): the player's own credentials in one place. */
export function AccountSettingsPage() {
  return (
    <div className="mt-4 space-y-6">
      <EmailCard />
      <PasswordCard />
      <TwoFactorCard />
      <ConnectedAccounts />
    </div>
  );
}
