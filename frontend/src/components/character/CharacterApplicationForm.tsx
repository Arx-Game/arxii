import { useState } from 'react';
import { useSendRosterApplication } from '../../roster/queries';
import { Textarea } from '../ui/textarea';
import { SubmitButton } from '../SubmitButton';
import type { RosterEntryData } from '../../roster/types';

interface CharacterApplicationFormProps {
  entryId: RosterEntryData['id'];
}

export function CharacterApplicationForm({ entryId }: CharacterApplicationFormProps) {
  const [message, setMessage] = useState('');
  const mutation = useSendRosterApplication(entryId);

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
