import { useFriendsQuery, useRemoveFriendMutation } from '../queries';

/** Your OOC friends list (#1727) — trusted RP partners across all your characters, with a login/
 * logoff watch alert. Separate from in-character relationships. Lists your friends with a remove
 * button; add a friend from another character's sheet. */
export function FriendsTab() {
  const { data, isLoading, isError } = useFriendsQuery();
  const remove = useRemoveFriendMutation();

  if (isLoading) return <p className="text-muted-foreground">Loading…</p>;
  if (isError) return <p className="text-destructive">Failed to load friends.</p>;

  const friends = data?.results ?? [];
  if (friends.length === 0) {
    return (
      <p className="text-muted-foreground">
        You have no friends listed yet. Visit another character's sheet to friend them.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <p className="text-sm text-muted-foreground">
        Your trusted RP partners (out-of-character). You get a login/logoff alert for each.
      </p>
      {friends.map((friend) => (
        <div key={friend.id} className="flex items-center justify-between rounded-md border p-3">
          <span>{friend.friend_name}</span>
          <button
            type="button"
            disabled={remove.isPending}
            className="rounded border px-2 py-1 text-sm hover:bg-accent disabled:opacity-50"
            onClick={() => remove.mutate(friend.id)}
          >
            Remove
          </button>
        </div>
      ))}
    </div>
  );
}
