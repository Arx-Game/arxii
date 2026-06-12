/**
 * AudereMajoraOfferDialog — the Crossing ceremony (#543).
 *
 * Renders the Audere Majora crossing offer: vision, eligible paths, declaration
 * textarea, advisory (VERBATIM), and risk text. Amber/gold palette to distinguish
 * from the fuchsia Audere gate.
 *
 * SPOILER RULE: vision_text / risk_text / advisory_text come from the server.
 * No invented ritual wording in this component.
 */

import { useEffect, useState } from 'react';
import { DoorOpen } from 'lucide-react';
import {
  AlertDialog,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import type { EligiblePath, PendingAudereMajoraOffer } from '@/magic/types';

interface AudereMajoraOfferDialogProps {
  offer: PendingAudereMajoraOffer;
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onAccept: (pathId: number, declarationText: string) => void;
  onDecline: () => void;
  isPending: boolean;
  /** When set, renders a role="alert" failure line above the footer. */
  errorMessage?: string | null;
}

export function AudereMajoraOfferDialog({
  offer,
  open,
  onOpenChange,
  onAccept,
  onDecline,
  isPending,
  errorMessage = null,
}: AudereMajoraOfferDialogProps) {
  const [selectedPathId, setSelectedPathId] = useState<number | null>(
    offer.intended_path_id ?? null
  );
  const [declaration, setDeclaration] = useState('');

  // Reset selection + declaration when the offer changes.
  useEffect(() => {
    setSelectedPathId(offer.intended_path_id ?? null);
    setDeclaration('');
  }, [offer.id, offer.intended_path_id]);

  const canAccept = selectedPathId !== null && declaration.trim().length > 0 && !isPending;

  return (
    <AlertDialog open={open} onOpenChange={onOpenChange}>
      <AlertDialogContent className="max-h-[90vh] overflow-y-auto border-amber-500/60 shadow-[0_0_60px_-12px] shadow-amber-500/50">
        <AlertDialogHeader>
          <AlertDialogTitle className="flex items-center gap-2 text-2xl font-bold tracking-wide text-amber-400">
            <DoorOpen className="h-7 w-7" />
            The Threshold Stands Before You
          </AlertDialogTitle>
          <AlertDialogDescription className="text-base">
            Standing at level{' '}
            <span className="font-semibold text-amber-400">{offer.boundary_level}</span>, crossing
            into{' '}
            <span className="font-semibold text-amber-400">{offer.target_stage_display}</span>.
          </AlertDialogDescription>
        </AlertDialogHeader>

        {/* Vision — player-only; strongly set apart */}
        {offer.vision_text ? (
          <blockquote
            data-testid="majora-vision"
            className="my-1 border-l-4 border-amber-500/60 bg-amber-950/20 px-4 py-3 font-serif italic text-amber-100"
          >
            {offer.vision_text}
          </blockquote>
        ) : null}

        {/* Path choice */}
        <div className="space-y-2">
          <p className="text-sm font-semibold text-amber-300">Choose your path</p>
          <div className="space-y-2">
            {offer.eligible_paths.map((path: EligiblePath) => (
              <label
                key={path.id}
                className={`flex cursor-pointer items-start gap-3 rounded-md border p-3 text-sm transition-colors ${
                  selectedPathId === path.id
                    ? 'border-amber-500/60 bg-amber-950/30 text-amber-100'
                    : 'border-border bg-muted/20 text-foreground hover:border-amber-500/30'
                }`}
              >
                <input
                  type="radio"
                  name="majora-path"
                  value={path.id}
                  checked={selectedPathId === path.id}
                  onChange={() => setSelectedPathId(path.id)}
                  className="mt-0.5 accent-amber-500"
                  disabled={isPending}
                />
                <div className="space-y-0.5">
                  <div className="font-semibold">
                    {path.name}{' '}
                    <span className="font-normal text-muted-foreground">— {path.stage_display}</span>
                  </div>
                  {path.description ? (
                    <div className="text-muted-foreground">{path.description}</div>
                  ) : null}
                </div>
              </label>
            ))}
          </div>
        </div>

        {/* Declaration */}
        <div className="space-y-1.5">
          <label
            htmlFor="majora-declaration"
            className="block text-sm font-semibold text-amber-300"
          >
            Speak — in your own words
          </label>
          <Textarea
            id="majora-declaration"
            data-testid="majora-declaration"
            value={declaration}
            onChange={(e) => setDeclaration(e.target.value)}
            disabled={isPending}
            placeholder="Declare your crossing…"
            className="min-h-[80px] border-amber-500/40 bg-amber-950/10 focus-visible:ring-amber-500/50"
          />
        </div>

        {/* Advisory — VERBATIM (same rule as Audere) */}
        {offer.advisory_text ? (
          <div
            role="alert"
            className="rounded-md border border-red-600/60 bg-red-950/40 p-3 text-sm font-medium text-red-200"
          >
            {offer.advisory_text}
          </div>
        ) : null}

        {/* Risk text */}
        {offer.risk_text ? (
          <div
            role="alert"
            className="rounded-md border border-red-600/60 bg-red-950/40 p-3 text-sm font-medium text-red-200"
          >
            {offer.risk_text}
          </div>
        ) : null}

        {/* Mutation error */}
        {errorMessage ? (
          <div
            role="alert"
            data-testid="audere-majora-respond-error"
            className="rounded-md border border-red-600/60 bg-red-950/40 p-3 text-sm font-medium text-red-200"
          >
            {errorMessage}
          </div>
        ) : null}

        <AlertDialogFooter>
          <Button variant="outline" onClick={onDecline} disabled={isPending}>
            Turn Away
          </Button>
          <Button
            className="bg-amber-600 text-white hover:bg-amber-500"
            onClick={() => {
              if (selectedPathId !== null) {
                onAccept(selectedPathId, declaration.trim());
              }
            }}
            disabled={!canAccept}
          >
            <DoorOpen className="mr-1.5 h-4 w-4" />
            Cross the Threshold
          </Button>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
