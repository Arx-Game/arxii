import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { CharacterLink } from '@/components/character';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { useDispatchPlayerAction } from '@/combat/queries';
import { fetchScenes, SceneListItem } from '../queries';

export function ScenesListPage() {
  const [status, setStatus] = useState('active');
  const { data } = useQuery<{ results: SceneListItem[] }>({
    queryKey: ['scenes', status],
    queryFn: () => fetchScenes(`status=${status}`),
  });

  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const characterId = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacterName)?.character_id ?? null,
    [myRosterEntries, activeCharacterName]
  );
  const { mutate: dispatchTravel, isPending } = useDispatchPlayerAction(characterId ?? 0);

  const goThere = (roomId: number) => {
    dispatchTravel({
      ref: { backend: 'registry', registry_key: 'travel_to' },
      kwargs: { target: roomId },
    });
  };

  return (
    <div className="container mx-auto p-4">
      <div className="mb-4">
        <select value={status} onChange={(e) => setStatus(e.target.value)} className="border p-2">
          <option value="active">Active</option>
          <option value="completed">Completed</option>
          <option value="upcoming">Upcoming</option>
        </select>
      </div>
      <table className="w-full border-collapse">
        <thead>
          <tr>
            <th className="border p-2 text-left">Name</th>
            <th className="border p-2 text-left">Description</th>
            <th className="border p-2 text-left">Date</th>
            <th className="border p-2 text-left">Location</th>
            <th className="border p-2 text-left">Participants</th>
          </tr>
        </thead>
        <tbody>
          {data?.results?.length === 0 && (
            <tr>
              <td colSpan={5} className="border p-4 text-center text-muted-foreground">
                No scenes here yet.
              </td>
            </tr>
          )}
          {data?.results?.map((scene) => (
            <tr key={scene.id}>
              <td className="border p-2">
                <Link to={`/scenes/${scene.id}`} className="text-blue-600 hover:underline">
                  {scene.name}
                </Link>
              </td>
              <td className="border p-2">{scene.description}</td>
              <td className="border p-2">{new Date(scene.date_started).toLocaleDateString()}</td>
              <td className="border p-2">
                {scene.location?.name || ''}
                {scene.location && (
                  <button
                    type="button"
                    className="ml-2 text-xs text-blue-600 hover:underline"
                    onClick={() => goThere(scene.location!.id)}
                    disabled={isPending}
                    data-testid={`go-there-${scene.id}`}
                  >
                    Go there
                  </button>
                )}
              </td>
              <td className="border p-2">
                {scene.participants.map((p, idx) => (
                  <span key={p.id}>
                    {p.roster_entry ? (
                      <CharacterLink
                        id={p.roster_entry.id}
                        className="text-blue-600 hover:underline"
                      >
                        {p.name}
                      </CharacterLink>
                    ) : (
                      p.name
                    )}
                    {idx < scene.participants.length - 1 && ', '}
                  </span>
                ))}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
