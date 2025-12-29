import { useState } from 'react';
import { Link } from 'react-router-dom';
import { useSendRosterApplication } from '@/roster/queries';
import { useAccount } from '@/store/hooks';
import { Textarea } from '../ui/textarea';
import { SubmitButton } from '../SubmitButton';
import type { RosterEntryData } from '@/roster/types';

interface CharacterApplicationFormProps {
  entryId: RosterEntryData['id'];
}

export function CharacterApplicationForm({ entryId }: CharacterApplicationFormProps) {
  const [message, setMessage] = useState('');
  const mutation = useSendRosterApplication(entryId);
  const account = useAccount();

  const isEmailVerified = account?.email_verified ?? false;

  // Show warning if email not verified
  if (!isEmailVerified) {
    return (
      <section>
        <h3 className="text-xl font-semibold">Apply to Play</h3>
        <div className="rounded-md border border-yellow-200 bg-yellow-50 p-4">
          <p className="text-sm text-yellow-800">
            Email verification required to apply for characters.{' '}
            <Link to="/account/unverified" className="font-medium underline">
              Verify your email →
            </Link>
          </p>
        </div>
      </section>
    );
  }

  return (
    <section>
      <h3 className="text-xl font-semibold">Apply to Play</h3>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate(message);
          setMessage('');
        }}
        className="space-y-2"
      >
        <Textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Why do you want to play this character?"
        />
        <SubmitButton isLoading={mutation.isPending} disabled={!message}>
          Send Application
        </SubmitButton>
      </form>
      {mutation.isError && <p className="text-red-600">Failed to send application.</p>}
    </section>
  );
}
