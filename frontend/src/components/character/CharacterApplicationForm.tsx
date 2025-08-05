import { useState } from 'react';
import { useSendRosterApplication } from '../../evennia_replacements/queries';

interface CharacterApplicationFormProps {
  entryId: number;
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
        <textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          className="w-full rounded border p-2"
          placeholder="Why do you want to play this character?"
        />
        <button type="submit" className="rounded bg-primary px-4 py-2 text-primary-foreground">
          Send Application
        </button>
      </form>
      {mutation.isError && <p className="text-red-600">Failed to send application.</p>}
    </section>
  );
}
