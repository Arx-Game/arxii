import { useState } from 'react';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Card, CardContent } from '@/components/ui/card';
import { ApiError, extractErrorMessage } from '@/lib/errors';

import { clockTime, speedInWords } from './clockDate';
import { usePauseClock, useResumeClock, useStaffClock } from './queries';
import { RecentChanges } from './RecentChanges';
import { SetDateDialog } from './SetDateDialog';
import { SpeedDialog } from './SpeedDialog';

/** Where the one clock row is created when none exists (the Django admin's Add form). */
const ADD_CLOCK_URL = '/admin/arxii/gameclock/add/';

function capitalize(word: string): string {
  return word.charAt(0).toUpperCase() + word.slice(1);
}

/** Running or Paused, as a pill. Shared with the staff hub's card. */
export function ClockStatePill({ paused }: { paused: boolean }) {
  return paused ? (
    <Badge variant="outline" className="border-amber-600/50 text-amber-700 dark:text-amber-400">
      Paused
    </Badge>
  ) : (
    <Badge
      variant="outline"
      className="border-emerald-600/50 text-emerald-700 dark:text-emerald-400"
    >
      Running
    </Badge>
  );
}

/**
 * The staff hub's Game clock page (#5248): pause the clock, resume it from the date it
 * shows, set the date, change the speed, and read who changed it.
 */
export function GameClockPage() {
  const { data: clock, error, isPending } = useStaffClock();
  const pause = usePauseClock();
  const resume = useResumeClock();
  const [settingDate, setSettingDate] = useState(false);
  const [changingSpeed, setChangingSpeed] = useState(false);

  const noClock = error instanceof ApiError && error.status === 503;
  const actionError = pause.error ?? resume.error;
  const busy = pause.isPending || resume.isPending;

  return (
    <div className="container mx-auto max-w-4xl space-y-8 px-4 py-8">
      <h1 className="text-2xl font-bold">Game clock</h1>

      {isPending && <p className="text-sm text-muted-foreground">Reading the clock.</p>}

      {noClock && (
        <p className="text-sm">
          No game clock exists yet.{' '}
          <a className="underline" href={ADD_CLOCK_URL}>
            Create it in the admin
          </a>
          .
        </p>
      )}

      {error && !noClock && (
        <p role="alert" className="text-sm text-destructive">
          {extractErrorMessage(error)}
        </p>
      )}

      {clock && (
        <Card>
          <CardContent className="space-y-3 pt-6">
            <div className="flex flex-wrap items-center gap-3">
              <ClockStatePill paused={clock.paused} />
              <span className="text-sm text-muted-foreground">
                {speedInWords(clock.time_ratio)}
              </span>
            </div>
            <p className="text-2xl font-semibold">{clock.date_display}</p>
            <p className="text-sm tabular-nums text-muted-foreground">
              {clockTime(clock.hour, clock.minute)} · {capitalize(clock.season)} ·{' '}
              {capitalize(clock.phase)}
            </p>
            <div className="flex flex-wrap gap-2 pt-2">
              {clock.paused ? (
                <Button disabled={busy} onClick={() => resume.mutate()}>
                  Resume from this date
                </Button>
              ) : (
                <Button disabled={busy} onClick={() => pause.mutate()}>
                  Pause
                </Button>
              )}
              <Button variant="outline" onClick={() => setSettingDate(true)}>
                Set the date
              </Button>
              <Button variant="outline" onClick={() => setChangingSpeed(true)}>
                Change speed
              </Button>
            </div>
            {actionError && (
              <p role="alert" className="text-sm text-destructive">
                {extractErrorMessage(actionError)}
              </p>
            )}
          </CardContent>
        </Card>
      )}

      {clock && (
        <>
          <SetDateDialog clock={clock} open={settingDate} onOpenChange={setSettingDate} />
          <SpeedDialog clock={clock} open={changingSpeed} onOpenChange={setChangingSpeed} />
          <RecentChanges />
        </>
      )}
    </div>
  );
}
