import { Link } from 'react-router-dom';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { CharacterAvatarLink } from './character';
import { urls } from '@/utils/urls';
import type { SceneSummary } from '@/scenes/types';

interface SceneListCardProps {
  title: string;
  scenes: SceneSummary[];
  emptyMessage: string;
}

export function SceneListCard({ title, scenes, emptyMessage }: SceneListCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>{title}</CardTitle>
      </CardHeader>
      <CardContent className="grid gap-4">
        {scenes.map((scene) => (
          <div key={scene.id} className="flex items-center gap-2">
            <div className="flex -space-x-2">
              {scene.participants
                .filter((p) => p.roster_entry)
                .map((p) => (
                  <CharacterAvatarLink
                    key={p.id}
                    id={p.roster_entry.id}
                    name={p.roster_entry.name}
                    avatarUrl={p.roster_entry.profile_url}
                    className="h-8 w-8 border hover:border-primary"
                    fallback={p.roster_entry.name?.charAt(0) || '?'}
                  />
                ))}
            </div>
            <Link to={urls.scene(scene.id)} className="font-medium hover:text-primary">
              {scene.name}
            </Link>
          </div>
        ))}
        {!scenes.length && <p className="text-sm text-muted-foreground">{emptyMessage}</p>}
      </CardContent>
    </Card>
  );
}
