/**
 * StaffSecretsPanel — the staff omniscient authoring surface for a character's secrets
 * (#3266), mounted only for `account.is_staff` viewers on the character sheet page.
 *
 * Deliberately unscoped by viewer knowledge — unlike SecretsTab (what the ACTIVE viewing
 * character knows), this shows every authored secret about the subject, "Unknown" layers
 * and all, and lets staff mint or edit one via AuthorSecretDialog.
 */

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';

import { useAuthoredSecretsQuery } from '../queries';
import type { AuthoredSecret } from '../types';

import { AuthorSecretDialog } from './AuthorSecretDialog';

const CONTENT_PREVIEW_LENGTH = 120;

function previewContent(content: string): string {
  if (content.length <= CONTENT_PREVIEW_LENGTH) return content;
  return `${content.slice(0, CONTENT_PREVIEW_LENGTH)}…`;
}

function SecretRow({ subjectId, secret }: { subjectId: number; secret: AuthoredSecret }) {
  return (
    <TableRow>
      <TableCell>{secret.level_display}</TableCell>
      <TableCell>{secret.category_name || 'Unknown'}</TableCell>
      <TableCell>{secret.subject_aware ? 'Yes' : 'No'}</TableCell>
      <TableCell>{secret.provenance_display}</TableCell>
      <TableCell className="max-w-sm truncate" title={secret.content ?? ''}>
        {previewContent(secret.content ?? '')}
      </TableCell>
      <TableCell>
        <AuthorSecretDialog
          subjectId={subjectId}
          secret={secret}
          trigger={
            <Button variant="outline" size="sm">
              Edit
            </Button>
          }
        />
      </TableCell>
    </TableRow>
  );
}

/** The staff secrets panel for `subjectId` (a CharacterSheet pk). Callers gate this on
 * `account?.is_staff` — the backend also enforces `IsAdminUser`, so a non-staff render
 * would just 403, but the caller-side gate keeps the panel from flashing for a beat. */
export function StaffSecretsPanel({ subjectId }: { subjectId: number }) {
  const { data, isLoading, isError } = useAuthoredSecretsQuery(subjectId);
  const secrets = data?.results ?? [];

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between space-y-0">
        <CardTitle>Secrets (staff)</CardTitle>
        <AuthorSecretDialog
          subjectId={subjectId}
          trigger={
            <Button size="sm" data-testid="author-secret-trigger">
              Author secret
            </Button>
          }
        />
      </CardHeader>
      <CardContent>
        {isLoading && <p className="text-muted-foreground">Loading…</p>}
        {isError && <p className="text-destructive">Failed to load authored secrets.</p>}
        {!isLoading && !isError && secrets.length === 0 && (
          <p className="text-muted-foreground">No secrets authored about this character yet.</p>
        )}
        {!isLoading && !isError && secrets.length > 0 && (
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Level</TableHead>
                <TableHead>Category</TableHead>
                <TableHead>Subject aware</TableHead>
                <TableHead>Provenance</TableHead>
                <TableHead>Content</TableHead>
                <TableHead />
              </TableRow>
            </TableHeader>
            <TableBody>
              {secrets.map((secret) => (
                <SecretRow key={secret.id} subjectId={subjectId} secret={secret} />
              ))}
            </TableBody>
          </Table>
        )}
      </CardContent>
    </Card>
  );
}
