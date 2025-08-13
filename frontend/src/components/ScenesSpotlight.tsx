import { useQuery } from '@tanstack/react-query';
import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Avatar, AvatarImage, AvatarFallback } from './ui/avatar';
import { apiFetch } from '../evennia_replacements/api';
import { urls } from '../utils/urls';

interface RosterEntry {
  id: number;
  name: string;
  profile_url?: string;
}

interface SceneParticipant {
  id: number;
  name: string;
  roster_entry: RosterEntry;
}

interface Scene {
  id: number;
  name: string;
  participants: SceneParticipant[];
}

interface ScenesSpotlightData {
  in_progress: Scene[];
  recent: Scene[];
}

async function fetchScenesSpotlight(): Promise<ScenesSpotlightData> {
  const res = await apiFetch('/api/scenes/spotlight/');
  if (!res.ok) {
    throw new Error('Failed to load scenes');
  }
  return res.json();
}

export function ScenesSpotlight() {
  const { data } = useQuery({
    queryKey: ['scenes', 'spotlight'],
    queryFn: fetchScenesSpotlight,
  });

  return (
    <section className="container mx-auto grid gap-4 py-8 md:grid-cols-2">
      <Card>
        <CardHeader>
          <CardTitle>In Progress</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4">
          {data?.in_progress.map((scene) => (
            <div key={scene.id} className="flex items-center gap-2">
              <div className="flex -space-x-2">
                {scene.participants.map((p) => (
                  <Link key={p.id} to={urls.character(p.roster_entry.id)}>
                    <Avatar className="h-8 w-8 border hover:border-primary">
                      {p.roster_entry.profile_url ? (
                        <AvatarImage src={p.roster_entry.profile_url} alt={p.roster_entry.name} />
                      ) : (
                        <AvatarFallback>{p.roster_entry.name?.charAt(0) || '?'}</AvatarFallback>
                      )}
                    </Avatar>
                  </Link>
                ))}
              </div>
              <Link to={urls.scene(scene.id)} className="font-medium hover:text-primary">
                {scene.name}
              </Link>
            </div>
          ))}
          {!data?.in_progress?.length && (
            <p className="text-sm text-muted-foreground">No active scenes.</p>
          )}
        </CardContent>
      </Card>
      <Card>
        <CardHeader>
          <CardTitle>Recently Concluded</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4">
          {data?.recent.map((scene) => (
            <div key={scene.id} className="flex items-center gap-2">
              <div className="flex -space-x-2">
                {scene.participants.map((p) => (
                  <Link key={p.id} to={urls.character(p.roster_entry.id)}>
                    <Avatar className="h-8 w-8 border hover:border-primary">
                      {p.roster_entry.profile_url ? (
                        <AvatarImage src={p.roster_entry.profile_url} alt={p.roster_entry.name} />
                      ) : (
                        <AvatarFallback>{p.roster_entry.name?.charAt(0) || '?'}</AvatarFallback>
                      )}
                    </Avatar>
                  </Link>
                ))}
              </div>
              <Link to={urls.scene(scene.id)} className="font-medium hover:text-primary">
                {scene.name}
              </Link>
            </div>
          ))}
          {!data?.recent?.length && (
            <p className="text-sm text-muted-foreground">No recently concluded scenes.</p>
          )}
        </CardContent>
      </Card>
    </section>
  );
}
