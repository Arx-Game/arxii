import { useSyncExternalStore } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { Button } from '@/components/ui/button';
import { connectionDiagnostics } from './connectionDiagnostics';

function useDiagnosticsSnapshot() {
  return useSyncExternalStore(
    (listener) => connectionDiagnostics.subscribe(listener),
    () => connectionDiagnostics.getSnapshot(),
    () => connectionDiagnostics.getSnapshot()
  );
}

/** Local-only alpha recorder controls. The component never owns socket listeners. */
export function ConnectionDiagnosticsSettings() {
  const snapshot = useDiagnosticsSnapshot();
  const size = new Blob([JSON.stringify(snapshot.events)]).size;
  return (
    <Card>
      <CardHeader>
        <CardTitle>Connection diagnostics</CardTitle>
        <CardDescription>
          Optional local metadata helps staff match browser socket events with private Portal logs.
          No game text, commands, account names, or credentials are retained. Review any download
          before sharing it through the private incident path, never a public issue.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center justify-between gap-4">
          <div>
            <Label htmlFor="connection-diagnostics-enabled">Diagnostics enabled</Label>
            <p className="text-sm text-muted-foreground">
              {snapshot.captureEnabled
                ? 'Metadata is retained in this browser tab.'
                : 'Capture is off.'}
            </p>
          </div>
          <Switch
            id="connection-diagnostics-enabled"
            checked={snapshot.captureEnabled}
            onCheckedChange={(enabled) => connectionDiagnostics.setEnabled(enabled)}
            aria-label="Diagnostics enabled"
          />
        </div>
        <p className="text-sm text-muted-foreground" data-testid="diagnostics-status">
          {snapshot.events.length} events · approximately {size} bytes ·{' '}
          {snapshot.events[0]?.wallTime ?? 'no events'}
          {snapshot.droppedEvents ? ` · ${snapshot.droppedEvents} dropped` : ''}
          {!snapshot.storageAvailable ? ' · browser storage unavailable' : ''}
        </p>
        <div className="flex flex-wrap gap-2">
          <Button
            type="button"
            variant="outline"
            disabled={!snapshot.captureEnabled}
            onClick={() => void connectionDiagnostics.download()}
          >
            Download connection diagnostics
          </Button>
          <Button type="button" variant="outline" onClick={() => connectionDiagnostics.clear()}>
            Clear diagnostics
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={!snapshot.captureEnabled}
            onClick={() => connectionDiagnostics.newRun()}
          >
            New run
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={!snapshot.captureEnabled}
            onClick={() => connectionDiagnostics.marker()}
          >
            Mark reconnect now
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
