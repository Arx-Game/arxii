import { useState } from 'react';

import { useAddFriendMutation } from '../queries';

/** "Friend this character" — shown on another character's sheet (#1727). Adds an OOC friendship
 * from your active character (default) or all your characters. `viewerEntryId` is your active
 * RosterEntry; `targetEntryId` is the viewed character's RosterEntry. */
export function FriendButton({
  viewerEntryId,
  targetEntryId,
  targetName,
}: {
  viewerEntryId: number | null;
  targetEntryId: number;
  targetName: string;
}) {
  const add = useAddFriendMutation();
  const [allCharacters, setAllCharacters] = useState(false);

  if (viewerEntryId === null) return null;

  if (add.isSuccess) {
    return (
      <span className="text-sm italic text-muted-foreground">Added {targetName} as a friend.</span>
    );
  }

  return (
    <div className="flex flex-wrap items-center gap-3">
      <button
        type="button"
        disabled={add.isPending}
        className="rounded border px-3 py-1 text-sm hover:bg-accent disabled:opacity-50"
        onClick={() => add.mutate({ viewer: viewerEntryId, friend: targetEntryId, allCharacters })}
      >
        + Friend {targetName}
      </button>
      <label className="flex items-center gap-1 text-xs text-muted-foreground">
        <input
          type="checkbox"
          checked={allCharacters}
          onChange={(event) => setAllCharacters(event.target.checked)}
        />
        from all my characters
      </label>
      {add.isError && (
        <span className="text-sm text-destructive">{(add.error as Error).message}</span>
      )}
    </div>
  );
}
