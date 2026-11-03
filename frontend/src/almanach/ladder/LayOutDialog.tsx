/**
 * LayOutDialog (#4983 slice 2, #4986): the owner pastes a realm's layout, Preview
 * shows what the walk would plant (per kingdom: counts, duchies with their pips, the
 * names drawn, charters, claims, refusals), Lay out plants it. The last text is kept
 * per realm in localStorage, a convenience only.
 */
import { useEffect, useState } from 'react';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogFooter,
  DialogTitle,
  NO_DESCRIPTION,
} from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';

export interface LayoutKingdomReport {
  name: string;
  line_no: number;
  planted: Record<string, number>;
  duchies: { name: string; pips: number; capital: boolean }[];
  names: string[];
  charters: string[];
  claims: string[];
  refusals: string[];
}

export interface LayoutReport {
  kingdoms: LayoutKingdomReport[];
  refusals: string[];
  wrote: boolean;
}

interface LayOutDialogProps {
  open: boolean;
  realmId: number;
  realmName: string;
  onClose: () => void;
  onPreview: (layout: string) => Promise<LayoutReport | null | undefined>;
  onLayOut: (layout: string) => Promise<LayoutReport | null | undefined>;
}

function storageKey(realmId: number) {
  return `almanach:layout:${realmId}`;
}

function readRemembered(realmId: number): string {
  try {
    return window.localStorage.getItem(storageKey(realmId)) ?? '';
  } catch {
    return '';
  }
}

function remember(realmId: number, text: string) {
  try {
    window.localStorage.setItem(storageKey(realmId), text);
  } catch {
    // storage unavailable: the text still went to the server
  }
}

export function LayOutDialog({
  open,
  realmId,
  realmName,
  onClose,
  onPreview,
  onLayOut,
}: LayOutDialogProps) {
  const [text, setText] = useState(() => readRemembered(realmId));
  const [report, setReport] = useState<LayoutReport | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setText(readRemembered(realmId));
      setReport(null);
    }
  }, [open, realmId]);

  const run = async (send: (layout: string) => Promise<LayoutReport | null | undefined>) => {
    setBusy(true);
    try {
      remember(realmId, text);
      const result = await send(text);
      setReport(result ?? null);
      return result ?? null;
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-3xl" {...NO_DESCRIPTION}>
        <DialogTitle>Lay out {realmName}</DialogTitle>
        <div className="grid gap-2">
          <Label htmlFor="layout-text">layout</Label>
          <textarea
            id="layout-text"
            className="min-h-40 w-full rounded-md border bg-background p-2 font-mono text-sm"
            value={text}
            onChange={(event) => setText(event.target.value)}
            spellCheck={false}
          />
        </div>
        {report && <LayoutReportView report={report} />}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            type="button"
            variant="outline"
            disabled={busy || !text.trim()}
            onClick={() => void run(onPreview)}
          >
            Preview
          </Button>
          <Button
            type="button"
            disabled={busy || !text.trim()}
            onClick={() =>
              void run(onLayOut).then((result) => {
                if (result?.wrote) onClose();
              })
            }
          >
            Lay out
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function LayoutReportView({ report }: { report: LayoutReport }) {
  return (
    <div className="grid gap-3 text-sm">
      {report.kingdoms.map((kingdom) => (
        <section
          key={`${kingdom.line_no}-${kingdom.name}`}
          data-testid={`layout-kingdom-${kingdom.name || kingdom.line_no}`}
          className="rounded-md border p-2"
        >
          <h4 className="font-semibold">
            {kingdom.name || 'unnamed'}{' '}
            <span className="font-normal text-muted-foreground">line {kingdom.line_no}</span>
          </h4>
          {Object.keys(kingdom.planted).length > 0 && (
            <p className="text-muted-foreground">
              {Object.entries(kingdom.planted)
                .map(([tier, count]) => `${count} ${tier}`)
                .join(' · ')}
            </p>
          )}
          {kingdom.duchies.length > 0 && (
            <table className="mt-1 w-full">
              <tbody>
                {kingdom.duchies.map((duchy) => (
                  <tr key={`${duchy.name}-${duchy.pips}`}>
                    <td>{duchy.name || 'unnamed'}</td>
                    <td className="text-right tabular-nums">{duchy.pips}</td>
                    <td className="pl-2 text-muted-foreground">{duchy.capital ? 'capital' : ''}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          {kingdom.charters.length > 0 && <p>{kingdom.charters.join('; ')}</p>}
          {kingdom.claims.map((claim) => (
            <p key={claim}>{claim}</p>
          ))}
          {kingdom.refusals.length > 0 && (
            <ul className="mt-1 text-destructive">
              {kingdom.refusals.map((refusal) => (
                <li key={refusal}>{refusal}</li>
              ))}
            </ul>
          )}
        </section>
      ))}
    </div>
  );
}
