import { useQuery } from '@tanstack/react-query';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Avatar, AvatarImage, AvatarFallback } from './ui/avatar';
import { apiFetch } from '../evennia_replacements/api';

interface SceneParticipant {
  id: number;
  name: string;
  avatar_url?: string;
}

interface Scene {
  id: number;
  title: string;
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
                  <Avatar key={p.id} className="h-8 w-8 border">
                    {p.avatar_url ? (
                      <AvatarImage src={p.avatar_url} alt={p.name} />
                    ) : (
                      <AvatarFallback>{p.name.charAt(0)}</AvatarFallback>
                    )}
                  </Avatar>
                ))}
              </div>
              <span className="font-medium">{scene.title}</span>
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
                  <Avatar key={p.id} className="h-8 w-8 border">
                    {p.avatar_url ? (
                      <AvatarImage src={p.avatar_url} alt={p.name} />
                    ) : (
                      <AvatarFallback>{p.name.charAt(0)}</AvatarFallback>
                    )}
                  </Avatar>
                ))}
              </div>
              <span className="font-medium">{scene.title}</span>
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
