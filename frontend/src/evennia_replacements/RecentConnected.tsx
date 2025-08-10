import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/card';
import { Avatar, AvatarImage, AvatarFallback } from '../components/ui/avatar';
import { Skeleton } from '../components/ui/skeleton';

interface RecentConnectedProps {
  accounts?: Array<{ username: string; avatar_url?: string }>;
  isLoading: boolean;
}

export function RecentConnected({ accounts, isLoading }: RecentConnectedProps) {
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
            {accounts?.map((acc) => (
              <li key={acc.username} className="flex items-center gap-2">
                <Avatar>
                  <AvatarImage src={acc.avatar_url} />
                  <AvatarFallback>{acc.username.slice(0, 2).toUpperCase()}</AvatarFallback>
                </Avatar>
                <span className="text-sm">{acc.username}</span>
              </li>
            ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
