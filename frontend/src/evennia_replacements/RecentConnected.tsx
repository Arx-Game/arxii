import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/card';
import { Avatar, AvatarImage, AvatarFallback } from '../components/ui/avatar';
import { Skeleton } from '../components/ui/skeleton';
import { Link } from 'react-router-dom';

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
                <Avatar>
                  <AvatarImage src={entry.avatar_url} />
                  <AvatarFallback>{(entry.name || '??').slice(0, 2).toUpperCase()}</AvatarFallback>
                </Avatar>
                <Link to={`/characters/${entry.id}`} className="text-sm underline">
                  {entry.name}
                </Link>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
