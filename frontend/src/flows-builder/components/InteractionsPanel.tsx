/**
 * InteractionsPanel — read-only summary of a flow's wiring: which trigger
 * definitions run it, what events it emits and who listens for them, and
 * what service functions it calls (#3417 task 11).
 *
 * Rows that reference a TriggerDefinition link to its editor route, which
 * Task 12 adds (`/staff/flows-builder/trigger-definitions/:id`). The links
 * are inert until that route exists — no change needed here once it lands.
 */
import { Link } from 'react-router-dom';

import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import type { FlowInteractions } from '../types';

function triggerDefinitionRoute(id: number): string {
  return `/staff/flows-builder/trigger-definitions/${id}`;
}

interface InteractionsPanelProps {
  interactions: FlowInteractions;
}

export function InteractionsPanel({ interactions }: InteractionsPanelProps) {
  return (
    <div className="space-y-4" data-testid="interactions-panel">
      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Run by</CardTitle>
        </CardHeader>
        <CardContent>
          {interactions.run_by.length === 0 ? (
            <p className="text-xs text-muted-foreground">No trigger definitions run this flow.</p>
          ) : (
            <ul className="space-y-2">
              {interactions.run_by.map((trigger) => (
                <li key={trigger.id} className="text-sm">
                  <Link
                    to={triggerDefinitionRoute(trigger.id)}
                    className="font-medium underline underline-offset-2"
                  >
                    {trigger.name}
                  </Link>{' '}
                  <span className="text-xs text-muted-foreground">on {trigger.event_name}</span>
                  {trigger.installing_templates.length > 0 ? (
                    <div className="pl-3 text-xs text-muted-foreground">
                      installed by:{' '}
                      {trigger.installing_templates.map((template) => template.name).join(', ')}
                    </div>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Emits</CardTitle>
        </CardHeader>
        <CardContent>
          {interactions.emits.length === 0 ? (
            <p className="text-xs text-muted-foreground">This flow emits no events.</p>
          ) : (
            <ul className="space-y-2">
              {interactions.emits.map((emit) => (
                <li key={emit.event_name} className="text-sm">
                  <span className="font-medium">{emit.event_name}</span>
                  {emit.listeners.length > 0 ? (
                    <div className="pl-3 text-xs text-muted-foreground">
                      listened for by:{' '}
                      {emit.listeners.map((listener, index) => (
                        <span key={listener.id}>
                          {index > 0 ? ', ' : ''}
                          <Link
                            to={triggerDefinitionRoute(listener.id)}
                            className="underline underline-offset-2"
                          >
                            {listener.name}
                          </Link>
                        </span>
                      ))}
                    </div>
                  ) : (
                    <div className="pl-3 text-xs text-muted-foreground">no listeners</div>
                  )}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-sm">Calls</CardTitle>
        </CardHeader>
        <CardContent>
          {interactions.calls.length === 0 ? (
            <p className="text-xs text-muted-foreground">This flow calls no service functions.</p>
          ) : (
            <ul className="space-y-1">
              {interactions.calls.map((name) => (
                <li key={name} className="font-mono text-xs">
                  {name}
                </li>
              ))}
            </ul>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
