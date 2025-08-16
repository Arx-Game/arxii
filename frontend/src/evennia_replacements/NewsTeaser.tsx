import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Table, TableBody, TableRow, TableCell } from '@/components/ui/table';
import { Skeleton } from '@/components/ui/skeleton';

interface NewsItem {
  id: number;
  title: string;
}

interface NewsTeaserProps {
  news?: NewsItem[];
  isLoading: boolean;
}

export function NewsTeaser({ news, isLoading }: NewsTeaserProps) {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Latest News</CardTitle>
      </CardHeader>
      <CardContent>
        {isLoading ? (
          <div className="space-y-2">
            {[0, 1, 2].map((i) => (
              <Skeleton key={i} className="h-4 w-full" />
            ))}
          </div>
        ) : (
          <Table>
            <TableBody>
              {news?.map((item) => (
                <TableRow key={item.id}>
                  <TableCell className="p-0 py-2 text-sm">{item.title}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
