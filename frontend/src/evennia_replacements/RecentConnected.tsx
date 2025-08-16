import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Skeleton } from '@/components/ui/skeleton';
import { CharacterAvatarLink, CharacterLink } from '@/components/character';

interface RecentConnectedProps {
  entries?: Array<{ id: number; name: string; avatar_url?: string }>;
  isLoading: boolean;
}

export function RecentConnected({ entries, isLoading }: RecentConnectedProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Recently Connected</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => (
              <div key={i} className="flex items-center gap-2">
                <Skeleton className="h-8 w-8 rounded-full" />
                <Skeleton className="h-4 w-1/3" />
              </div>
            ))}
          </div>
        ) : (
          <ul className="space-y-2">
            {entries?.map((entry) => (
              <li key={entry.id} className="flex items-center gap-2">
                <CharacterAvatarLink
                  id={entry.id}
                  name={entry.name}
                  avatarUrl={entry.avatar_url}
                  className="h-8 w-8"
                />
                <CharacterLink id={entry.id} className="text-sm underline">
                  {entry.name}
                </CharacterLink>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
