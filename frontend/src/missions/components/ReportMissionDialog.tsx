/**
 * ReportMissionDialog — the RESOLVED -> COMPLETE report affordance (#1753/#3040).
 *
 * A RESOLVED run is one whose reward lines are authored but not yet paid:
 * the player must find the report-to Functionary and choose how to report
 * before money/fame lands. This dialog offers the four styles the report
 * endpoint accepts and submits the choice. The server enforces co-location
 * with a Functionary of the report-to role; we surface its error message
 * verbatim rather than trying to guess reachability client-side.
 */
import { useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';

import { ApiValidationError, flattenErrorMessage } from '../api';
import { useReportMission } from '../queries';
import type { ReportStyle } from '../types';

const STYLE_OPTIONS: { value: ReportStyle; label: string; description: string }[] = [
  { value: 'accurate', label: 'Accurate', description: 'The straight account. Baseline pay.' },
  { value: 'humble', label: 'Humble', description: 'Play it down. Lower fame, same pay.' },
  {
    value: 'mostly_accurate',
    label: 'Mostly accurate',
    description: 'Talk around the risky parts. A check to dodge any fallout.',
  },
  {
    value: 'embellished',
    label: 'Embellished',
    description: 'Talk it up. A Persuasion check; success doubles the pay.',
  },
];

interface ReportMissionDialogProps {
  instanceId: number;
  templateName: string;
}

export function ReportMissionDialog({ instanceId, templateName }: ReportMissionDialogProps) {
  const [open, setOpen] = useState(false);
  const [style, setStyle] = useState<ReportStyle>('accurate');
  const report = useReportMission();

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => {
        setOpen(next);
        if (next) report.reset();
      }}
    >
      <DialogTrigger asChild>
        <Button size="sm" data-testid={`report-mission-${instanceId}`}>
          Report in
        </Button>
      </DialogTrigger>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Report {templateName}</DialogTitle>
          <DialogDescription>
            Choose how to tell it. You need to be standing with the right person to report to.
          </DialogDescription>
        </DialogHeader>
        <RadioGroup
          value={style}
          onValueChange={(val) => setStyle(val as ReportStyle)}
          className="flex flex-col gap-2"
          data-testid="report-style-group"
        >
          {STYLE_OPTIONS.map((option) => (
            <label
              key={option.value}
              className="flex cursor-pointer items-start gap-3 rounded-md border p-3 hover:bg-accent"
            >
              <RadioGroupItem
                value={option.value}
                id={`report-style-${option.value}`}
                className="mt-1"
              />
              <span>
                <span className="block text-sm font-medium">{option.label}</span>
                <span className="block text-xs text-muted-foreground">{option.description}</span>
              </span>
            </label>
          ))}
        </RadioGroup>
        {report.error ? (
          <p className="text-sm text-destructive" data-testid="report-mission-error">
            {report.error instanceof ApiValidationError
              ? flattenErrorMessage(report.error.fieldErrors)
              : report.error.message}
          </p>
        ) : null}
        <DialogFooter>
          <Button variant="outline" onClick={() => setOpen(false)}>
            Cancel
          </Button>
          <Button
            disabled={report.isPending}
            onClick={() =>
              report.mutate({ instanceId, style }, { onSuccess: () => setOpen(false) })
            }
            data-testid="report-mission-submit"
          >
            {report.isPending ? 'Reporting…' : 'Report'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
