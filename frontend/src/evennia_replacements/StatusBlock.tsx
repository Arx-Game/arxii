import { Card, CardContent } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';

import { useStatusQuery } from './queries';

export function StatusBlock() {
  const { data } = useStatusQuery();

  if (!data) {
    return null;
  }

  return (
    <Card className="w-fit">
      <CardContent className="flex items-center gap-2 p-4">
        <Badge>{data.online} online</Badge>
        <span className="text-sm text-muted-foreground">{data.accounts} total accounts</span>
      </CardContent>
    </Card>
  );
}
