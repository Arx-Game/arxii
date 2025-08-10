import { Card, CardHeader, CardTitle, CardContent } from '../components/ui/card';
import { Skeleton } from '../components/ui/skeleton';

interface StatsCardProps {
  stats?: Record<string, number>;
  isLoading: boolean;
}

export function StatsCard({ stats, isLoading }: StatsCardProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Stats</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-1/2" />
            <Skeleton className="h-4 w-1/3" />
            <Skeleton className="h-4 w-1/4" />
          </div>
        ) : (
          <ul className="space-y-1 text-sm">
            {stats &&
              Object.entries(stats).map(([label, value]) => (
                <li key={label} className="flex justify-between">
                  <span className="capitalize">{label.replace(/_/g, ' ')}</span>
                  <span className="font-medium">{value}</span>
                </li>
              ))}
          </ul>
        )}
      </CardContent>
    </Card>
  );
}
