import { useState } from 'react';
import { useSendRosterApplication } from '../../roster/queries';
import { Button } from '../ui/button';
import { Textarea } from '../ui/textarea';

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
        <Textarea
          value={message}
          onChange={(e) => setMessage(e.target.value)}
          placeholder="Why do you want to play this character?"
        />
        <Button type="submit">Send Application</Button>
      </form>
      {mutation.isError && <p className="text-red-600">Failed to send application.</p>}
    </section>
  );
}
