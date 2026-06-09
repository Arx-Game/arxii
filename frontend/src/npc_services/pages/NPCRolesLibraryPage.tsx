/**
 * NPC Roles library (#728 — Mission Studio).
 *
 * Lists NPCRole rows, supports name search + create, and links into the
 * per-role editor. Replaces the deleted GiverLibraryPage against the unified
 * npc-services surface.
 */
import { Loader2 } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';

import { ApiValidationError, flattenErrorMessage } from '../api';
import { useCreateRole, useRoles } from '../queries';

export function NPCRolesLibraryPage() {
  const [search, setSearch] = useState('');
  const { data, isLoading } = useRoles({ name: search || undefined });
  const roles = data?.results ?? [];

  return (
    <div className="container mx-auto max-w-4xl space-y-6 py-6">
      <div>
        <h1 className="text-2xl font-semibold">NPC Roles</h1>
        <p className="text-sm text-muted-foreground">
          Author the roles NPCs play and the services (missions, permits) they offer.
        </p>
      </div>

      <CreateRoleCard />

      <div className="space-y-3">
        <Input
          placeholder="Search roles by name…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Search roles"
        />

        {isLoading ? (
          <div className="flex justify-center py-8">
            <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
          </div>
        ) : roles.length === 0 ? (
          <p className="py-6 text-center text-sm text-muted-foreground">No roles found.</p>
        ) : (
          <ul className="space-y-2">
            {roles.map((role) => (
              <li key={role.id}>
                <Link to={`/staff/npc-services/roles/${role.id}`}>
                  <Card className="cursor-pointer transition-colors hover:bg-muted/50">
                    <CardContent className="py-3">
                      <div className="font-medium">{role.name}</div>
                      {role.description && (
                        <div className="line-clamp-1 text-sm text-muted-foreground">
                          {role.description}
                        </div>
                      )}
                    </CardContent>
                  </Card>
                </Link>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

function CreateRoleCard() {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const navigate = useNavigate();
  const createRole = useCreateRole();

  const submit = () => {
    if (!name.trim()) return;
    createRole.mutate(
      { name: name.trim() },
      { onSuccess: (role) => navigate(`/staff/npc-services/roles/${role.id}`) }
    );
  };

  if (!open) {
    return (
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        New role
      </Button>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">New role</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1">
          <Label htmlFor="new-role-name">Name</Label>
          <Input
            id="new-role-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. Dockside Fixer"
          />
        </div>
        {createRole.isError && (
          <p className="text-sm text-destructive">
            {createRole.error instanceof ApiValidationError
              ? flattenErrorMessage(createRole.error.fieldErrors)
              : 'Could not create the role.'}
          </p>
        )}
        <div className="flex gap-2">
          <Button size="sm" onClick={submit} disabled={!name.trim() || createRole.isPending}>
            {createRole.isPending ? 'Creating…' : 'Create'}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
