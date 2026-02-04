import { Folder, FileText } from 'lucide-react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

interface SubjectCardProps {
  name: string;
  hasChildren: boolean;
  onClick: () => void;
}

export function SubjectCard({ name, hasChildren, onClick }: SubjectCardProps) {
  return (
    <Card className="mb-4 cursor-pointer transition-colors hover:bg-accent/50" onClick={onClick}>
      <CardHeader className="pb-2">
        <div className="flex items-center gap-2">
          {hasChildren ? (
            <Folder className="h-5 w-5 text-muted-foreground" />
          ) : (
            <FileText className="h-5 w-5 text-muted-foreground" />
          )}
          <CardTitle className="text-lg">{name}</CardTitle>
        </div>
      </CardHeader>
      <CardContent />
    </Card>
  );
}
