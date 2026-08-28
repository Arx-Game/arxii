/**
 * FlowsBuilderPage — staff landing page for the flows authoring UI (#3417
 * task 11).
 *
 * Three tabs mirror the three rows flows-builder authors: FlowDefinition
 * ("Flows"), TriggerDefinition ("Trigger Definitions" — the reusable
 * event -> flow wiring, created via `TriggerDefinitionEditorPage`), and
 * Trigger ("Installed Triggers" — a TriggerDefinition attached to one
 * specific game object, created via `TriggerInstallDialog`) (#3417 task 12).
 */
import { Loader2 } from 'lucide-react';
import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { flattenErrorMessage } from '@/missions/api';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';

import { ApiValidationError } from '../api';
import { TriggerInstallDialog } from '../components/TriggerInstallDialog';
import {
  useCreateFlow,
  useDeleteTrigger,
  useDeleteTriggerDefinition,
  useFlows,
  useTriggerDefinitions,
  useTriggers,
} from '../queries';

export function FlowsBuilderPage() {
  return (
    <div className="container mx-auto max-w-5xl space-y-6 py-6">
      <div>
        <h1 className="text-2xl font-semibold">Flows Builder</h1>
        <p className="text-sm text-muted-foreground">
          Author flow definitions, the trigger definitions that run them, and the triggers
          installed on specific objects.
        </p>
      </div>

      <Tabs defaultValue="flows">
        <TabsList>
          <TabsTrigger value="flows">Flows</TabsTrigger>
          <TabsTrigger value="trigger-definitions">Trigger Definitions</TabsTrigger>
          <TabsTrigger value="triggers">Installed Triggers</TabsTrigger>
        </TabsList>
        <TabsContent value="flows">
          <FlowsTab />
        </TabsContent>
        <TabsContent value="trigger-definitions">
          <TriggerDefinitionsTab />
        </TabsContent>
        <TabsContent value="triggers">
          <InstalledTriggersTab />
        </TabsContent>
      </Tabs>
    </div>
  );
}

function FlowsTab() {
  const [search, setSearch] = useState('');
  const { data, isLoading } = useFlows(search || undefined);
  const flows = data?.results ?? [];

  return (
    <div className="space-y-4 pt-4">
      <CreateFlowCard />
      <Input
        placeholder="Search flows by name…"
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        aria-label="Search flows"
      />
      {isLoading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : flows.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">No flows found.</p>
      ) : (
        <ul className="space-y-2">
          {flows.map((flow) => (
            <li key={flow.id}>
              <Link to={`/staff/flows-builder/flows/${flow.id}`}>
                <Card className="cursor-pointer transition-colors hover:bg-muted/50">
                  <CardContent className="py-3">
                    <div className="flex items-center justify-between">
                      <div className="font-medium">{flow.name}</div>
                      <span className="text-xs text-muted-foreground">
                        {flow.step_count} step{flow.step_count === 1 ? '' : 's'}
                      </span>
                    </div>
                    {flow.description ? (
                      <div className="line-clamp-1 text-sm text-muted-foreground">
                        {flow.description}
                      </div>
                    ) : null}
                  </CardContent>
                </Card>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function CreateFlowCard() {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState('');
  const navigate = useNavigate();
  const createFlow = useCreateFlow();

  const submit = () => {
    if (!name.trim()) return;
    createFlow.mutate(
      { name: name.trim() },
      { onSuccess: (flow) => navigate(`/staff/flows-builder/flows/${flow.id}`) }
    );
  };

  if (!open) {
    return (
      <Button variant="outline" size="sm" onClick={() => setOpen(true)}>
        New flow
      </Button>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">New flow</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1">
          <Label htmlFor="new-flow-name">Name</Label>
          <Input
            id="new-flow-name"
            value={name}
            onChange={(e) => setName(e.target.value)}
            placeholder="e.g. grant_boon_on_enter"
          />
        </div>
        {createFlow.isError ? (
          <p className="text-sm text-destructive">
            {createFlow.error instanceof ApiValidationError
              ? flattenErrorMessage(createFlow.error.fieldErrors)
              : 'Could not create the flow.'}
          </p>
        ) : null}
        <div className="flex gap-2">
          <Button size="sm" onClick={submit} disabled={!name.trim() || createFlow.isPending}>
            {createFlow.isPending ? 'Creating…' : 'Create'}
          </Button>
          <Button size="sm" variant="ghost" onClick={() => setOpen(false)}>
            Cancel
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function TriggerDefinitionsTab() {
  const [search, setSearch] = useState('');
  const { data, isLoading } = useTriggerDefinitions({ search: search || undefined });
  const rows = data?.results ?? [];
  const deleteTd = useDeleteTriggerDefinition();
  const navigate = useNavigate();

  return (
    <div className="space-y-4 pt-4">
      <div className="flex items-center justify-between gap-2">
        <Input
          placeholder="Search trigger definitions by name…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Search trigger definitions"
        />
        <Button
          size="sm"
          variant="outline"
          onClick={() => navigate('/staff/flows-builder/trigger-definitions/new')}
        >
          New trigger definition
        </Button>
      </div>
      {isLoading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : rows.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">
          No trigger definitions found.
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Name</TableHead>
              <TableHead>Event</TableHead>
              <TableHead>Flow</TableHead>
              <TableHead>Priority</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((trigger) => (
              <TableRow key={trigger.id}>
                <TableCell className="font-medium">
                  <Link
                    to={`/staff/flows-builder/trigger-definitions/${trigger.id}`}
                    className="underline underline-offset-2"
                  >
                    {trigger.name}
                  </Link>
                </TableCell>
                <TableCell>{trigger.event_name}</TableCell>
                <TableCell>
                  <Link
                    to={`/staff/flows-builder/flows/${trigger.flow_definition}`}
                    className="underline underline-offset-2"
                  >
                    Flow #{trigger.flow_definition}
                  </Link>
                </TableCell>
                <TableCell>{trigger.priority}</TableCell>
                <TableCell>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      if (window.confirm(`Delete trigger definition "${trigger.name}"?`)) {
                        deleteTd.mutate(trigger.id);
                      }
                    }}
                  >
                    Delete
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}

function InstalledTriggersTab() {
  const [search, setSearch] = useState('');
  const [installOpen, setInstallOpen] = useState(false);
  const { data, isLoading } = useTriggers({ search: search || undefined });
  const rows = data?.results ?? [];
  const deleteTrigger = useDeleteTrigger();

  return (
    <div className="space-y-4 pt-4">
      <div className="flex items-center justify-between gap-2">
        <Input
          placeholder="Search installed triggers…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          aria-label="Search installed triggers"
        />
        <Button size="sm" variant="outline" onClick={() => setInstallOpen(true)}>
          Install trigger
        </Button>
      </div>
      <TriggerInstallDialog open={installOpen} onOpenChange={setInstallOpen} />
      {isLoading ? (
        <div className="flex justify-center py-8">
          <Loader2 className="h-5 w-5 animate-spin text-muted-foreground" />
        </div>
      ) : rows.length === 0 ? (
        <p className="py-6 text-center text-sm text-muted-foreground">
          No installed triggers found.
        </p>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Trigger definition</TableHead>
              <TableHead>Object</TableHead>
              <TableHead>Source condition</TableHead>
              <TableHead>Source stage</TableHead>
              <TableHead />
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row) => (
              <TableRow key={row.id}>
                <TableCell>
                  <Link
                    to={`/staff/flows-builder/trigger-definitions/${row.trigger_definition}`}
                    className="underline underline-offset-2"
                  >
                    #{row.trigger_definition}
                  </Link>
                </TableCell>
                <TableCell>#{row.obj}</TableCell>
                <TableCell>{row.source_condition ?? '—'}</TableCell>
                <TableCell>{row.source_stage ?? '—'}</TableCell>
                <TableCell>
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      if (window.confirm('Delete this installed trigger?')) {
                        deleteTrigger.mutate(row.id);
                      }
                    }}
                  >
                    Delete
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </div>
  );
}
