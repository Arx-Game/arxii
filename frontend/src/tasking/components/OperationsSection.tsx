/**
 * OperationsSection (#2820 phase 1) — the org task board panel on OrgPage.
 *
 * Read-only board: in-flight and resolved org tasks with status, target,
 * deadline, and (once resolved) the agent's report. Issue/assign affordances
 * ride later phases; staff author templates in admin today.
 */

import { Badge } from '@/components/ui/badge';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { useOrgTasksQuery } from '@/tasking/queries';
import type { OrgTask } from '@/tasking/api';

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'destructive' | 'outline'> = {
  open: 'outline',
  assigned: 'default',
  resolving: 'default',
  completed: 'secondary',
  failed: 'destructive',
  expired: 'destructive',
};

function TaskRow({ task }: { task: OrgTask }) {
  const fulfillment = task.fulfillment;
  return (
    <li className="rounded-md border p-3">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-medium">{task.template.name}</span>
        <Badge variant={STATUS_VARIANT[task.status ?? 'open'] ?? 'outline'}>{task.status}</Badge>
        {task.target_label && task.target_label !== 'the job' && (
          <span className="text-sm text-muted-foreground">→ {task.target_label}</span>
        )}
      </div>
      <div className="mt-1 text-sm text-muted-foreground">
        {fulfillment ? (
          <span>
            {fulfillment.agent_name || 'An agent'} · handled by {fulfillment.handler_name}
            {task.deadline && !fulfillment.resolved_at && (
              <> · due {new Date(task.deadline).toLocaleString()}</>
            )}
          </span>
        ) : (
          <span>Awaiting an agent</span>
        )}
      </div>
      {fulfillment?.resolved_at && fulfillment.report && (
        <p className="mt-2 border-l-2 pl-2 text-sm italic">{fulfillment.report}</p>
      )}
    </li>
  );
}

export function OperationsSection({ orgId }: { orgId: number }) {
  const { data: tasks = [] } = useOrgTasksQuery(orgId);

  if (tasks.length === 0) return null;

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-lg">Operations</CardTitle>
      </CardHeader>
      <CardContent>
        <ul className="space-y-2">
          {tasks.map((task) => (
            <TaskRow key={task.id} task={task} />
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
