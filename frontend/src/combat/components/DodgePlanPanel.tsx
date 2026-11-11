/**
 * DodgePlanPanel — "Reactions" (#4676, demo Screen 3).
 *
 * The dodge itself is automatic on the server; this sets whether to dodge and where to
 * land, through the `combat_dodge` registry action. Shown only when the viewer's own
 * participant row carries a `dodge_plan` (the server sends it to its owner only, and
 * only when something she has lets her dodge).
 *
 * #5066: the technique answering her dodges, whether to keep dodging into Soulfray, and
 * an automatic defensive thread pull, all through the `dodge_settings` registry action.
 */

import { useState } from 'react';
import { toast } from 'sonner';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { cn } from '@/lib/utils';
import type { components } from '@/generated/api';
import { useCharacterResonances } from '@/magic/queries';
import { isDispatchFailure, type DispatchActionRequest, type DispatchResult } from '@/combat/types';
import { dodgeRequest, dodgeSettingsRequest, steadyRequest } from '@/combat/dodging';
import { SoulfrayAcceptGate } from '@/combat/components/SoulfrayAcceptGate';

type DodgePlan = components['schemas']['DodgePlan'];
type SteadyPlan = components['schemas']['SteadyPlan'];

export interface DodgePlanPanelProps {
  plan: DodgePlan | null;
  /** Her sheet: the defensive pull picks from her resonances. */
  characterSheetId: number;
  /** Her steady plan, sent only when she holds the steadying capability. */
  steadyPlan?: SteadyPlan | null;
  /** The viewer's own place now: the first option is always where she stands. */
  currentPositionId: number | null;
  isLocked: boolean;
  dispatchAction: (params: DispatchActionRequest) => Promise<DispatchResult>;
  onDispatched?: () => void;
}

export function DodgePlanPanel({
  plan,
  characterSheetId,
  steadyPlan = null,
  currentPositionId,
  isLocked,
  dispatchAction,
  onDispatched,
}: DodgePlanPanelProps) {
  const send = (kwargs: Record<string, unknown>) => {
    dispatchPlan(dodgeRequest(kwargs));
  };

  const dispatchPlan = (request: DispatchActionRequest) => {
    dispatchAction(request)
      .then((result) => {
        if (isDispatchFailure(result)) {
          toast.error(result.message ?? 'That plan was refused.');
          return;
        }
        onDispatched?.();
      })
      .catch((err: unknown) => {
        toast.error(err instanceof Error ? err.message : 'That plan was refused.');
      });
  };

  return (
    <section className="space-y-1.5" data-testid="reactions">
      <h3 className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
        Reactions
      </h3>
      {plan && (
        <DodgeSection
          plan={plan}
          characterSheetId={characterSheetId}
          currentPositionId={currentPositionId}
          isLocked={isLocked}
          send={send}
          sendSettings={(kwargs) => dispatchPlan(dodgeSettingsRequest(kwargs))}
        />
      )}
      {steadyPlan && (
        <div className="space-y-1.5" data-testid="steady-plan">
          <div className="flex items-center gap-2 text-sm">
            <Switch
              id="steady-toggle"
              data-testid="steady-toggle"
              checked={steadyPlan.enabled}
              disabled={isLocked}
              onCheckedChange={(on) => dispatchPlan(steadyRequest(on))}
            />
            <label htmlFor="steady-toggle">Steady allies who lose to a compulsion</label>
          </div>
          <p className="text-xs text-muted-foreground" data-testid="steady-cost">
            ({steadyPlan.capability_name}) · {steadyPlan.cost_line} · {steadyPlan.bonus_hint}
          </p>
          <p className="text-xs text-muted-foreground" data-testid="reaction-shared-note">
            Each reaction this round makes the next one harder, steadying and dodging alike.
          </p>
        </div>
      )}
    </section>
  );
}

type Send = (kwargs: Record<string, unknown>) => void;

function DodgeSection({
  plan,
  characterSheetId,
  currentPositionId,
  isLocked,
  send,
  sendSettings,
}: {
  plan: DodgePlan;
  characterSheetId: number;
  currentPositionId: number | null;
  isLocked: boolean;
  send: Send;
  sendSettings: Send;
}) {
  const elsewhere = plan.options.filter((option) => option.id !== currentPositionId);
  const inPlace = plan.enabled && plan.landing_id === null;

  return (
    <div className="space-y-1.5" data-testid="dodge-plan">
      {plan.soulfray_check_in && (
        <SoulfrayAcceptGate
          warning={plan.soulfray_check_in}
          body="Your automatic dodges cast into Soulfray."
          acceptLabel="Keep dodging into Soulfray"
          accepted={plan.into_soulfray}
          onAcceptChange={(on) => sendSettings({ into_soulfray: on })}
          disabled={isLocked}
          testId="dodge-soulfray-check-in"
          checkboxTestId="dodge-soulfray-check-in-toggle"
        />
      )}
      <DodgeOption
        label="Dodge in place"
        chosen={inPlace}
        disabled={isLocked}
        testId="dodge-in-place"
        onClick={() => send({})}
      />
      {elsewhere.map((option) => (
        <DodgeOption
          key={option.id}
          label={`Dodge to ${option.name}`}
          chosen={plan.enabled && plan.landing_id === option.id}
          disabled={isLocked}
          testId={`dodge-to-${option.id}`}
          onClick={() => send({ position_id: option.id })}
        />
      ))}
      <DodgeOption
        label="Don't dodge"
        chosen={!plan.enabled}
        disabled={isLocked}
        testId="dodge-off"
        onClick={() => send({ dodge: false })}
      />
      <p className="text-xs text-muted-foreground" data-testid="dodge-cost">
        {plan.cost_line}
      </p>
      {plan.techniques.length > 0 && (
        <DodgeTechniquePicker plan={plan} isLocked={isLocked} sendSettings={sendSettings} />
      )}
      <div className="flex items-center gap-2 text-sm">
        <Switch
          id="dodge-into-soulfray"
          data-testid="dodge-into-soulfray"
          checked={plan.into_soulfray}
          disabled={isLocked}
          onCheckedChange={(on) => sendSettings({ into_soulfray: on })}
        />
        <label htmlFor="dodge-into-soulfray">Dodge even into Soulfray</label>
      </div>
      <AutoPullControls
        plan={plan}
        characterSheetId={characterSheetId}
        isLocked={isLocked}
        sendSettings={sendSettings}
      />
    </div>
  );
}

function DodgeTechniquePicker({
  plan,
  isLocked,
  sendSettings,
}: {
  plan: DodgePlan;
  isLocked: boolean;
  sendSettings: Send;
}) {
  const chosen = plan.techniques.find((t) => t.id === plan.technique_id) ?? null;

  return (
    <div className="space-y-1" data-testid="dodge-technique">
      <div className="flex items-center gap-2">
        <span className="text-xs text-muted-foreground">Dodge with</span>
        <Select
          value={chosen ? String(chosen.id) : ''}
          onValueChange={(value) => sendSettings({ technique_id: Number(value) })}
          disabled={isLocked}
        >
          <SelectTrigger
            data-testid="dodge-technique-select"
            aria-label="Dodge with"
            className="h-8 flex-1 text-xs"
          >
            <SelectValue placeholder="Choose a technique" />
          </SelectTrigger>
          <SelectContent>
            {plan.techniques.map((technique) => (
              <SelectItem key={technique.id} value={String(technique.id)}>
                {technique.is_default ? `${technique.name} (default)` : technique.name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        {chosen && !chosen.is_default && (
          <button
            type="button"
            data-testid="dodge-technique-save-default"
            disabled={isLocked}
            onClick={() => sendSettings({ technique_id: chosen.id, save_default: true })}
            className="rounded border border-border px-2 py-1 text-xs hover:bg-muted/50 disabled:cursor-not-allowed disabled:opacity-50"
          >
            Save as my default
          </button>
        )}
      </div>
      {chosen && (
        <p className="text-xs text-muted-foreground" data-testid="dodge-technique-cost">
          {chosen.cost_line}
        </p>
      )}
    </div>
  );
}

const PULL_TIERS = [1, 2, 3] as const;

function AutoPullControls({
  plan,
  characterSheetId,
  isLocked,
  sendSettings,
}: {
  plan: DodgePlan;
  characterSheetId: number;
  isLocked: boolean;
  sendSettings: Send;
}) {
  const { data: resonances } = useCharacterResonances(characterSheetId);
  const [resonanceId, setResonanceId] = useState<number | null>(plan.auto_pull_resonance_id);
  const [tier, setTier] = useState<number>(plan.auto_pull_tier ?? 1);

  const sendPull = (nextResonanceId: number | null, nextTier: number) => {
    if (nextResonanceId === null) return;
    sendSettings({ auto_pull: true, pull_resonance_id: nextResonanceId, pull_tier: nextTier });
  };

  return (
    <div className="space-y-1" data-testid="dodge-auto-pull">
      <div className="flex items-center gap-2 text-sm">
        <Switch
          id="dodge-auto-pull"
          data-testid="dodge-auto-pull-toggle"
          checked={plan.auto_pull}
          disabled={isLocked || (!plan.auto_pull && resonanceId === null)}
          onCheckedChange={(on) =>
            on ? sendPull(resonanceId, tier) : sendSettings({ auto_pull: false })
          }
        />
        <label htmlFor="dodge-auto-pull">Pull threads for defense when attacked</label>
      </div>
      <div className="flex gap-2">
        <Select
          value={resonanceId === null ? '' : String(resonanceId)}
          onValueChange={(value) => {
            setResonanceId(Number(value));
            if (plan.auto_pull) sendPull(Number(value), tier);
          }}
          disabled={isLocked}
        >
          <SelectTrigger
            data-testid="dodge-auto-pull-resonance"
            aria-label="Resonance"
            className="h-8 flex-1 text-xs"
          >
            <SelectValue placeholder="Resonance" />
          </SelectTrigger>
          <SelectContent>
            {(resonances ?? []).map((r) => (
              <SelectItem key={r.resonance} value={String(r.resonance)}>
                {r.resonance_name}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
        <Select
          value={String(tier)}
          onValueChange={(value) => {
            setTier(Number(value));
            if (plan.auto_pull) sendPull(resonanceId, Number(value));
          }}
          disabled={isLocked}
        >
          <SelectTrigger
            data-testid="dodge-auto-pull-tier"
            aria-label="Tier"
            className="h-8 w-24 text-xs"
          >
            <SelectValue />
          </SelectTrigger>
          <SelectContent>
            {PULL_TIERS.map((t) => (
              <SelectItem key={t} value={String(t)}>
                Tier {t}
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>
    </div>
  );
}

function DodgeOption({
  label,
  chosen,
  disabled,
  testId,
  onClick,
}: {
  label: string;
  chosen: boolean;
  disabled: boolean;
  testId: string;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      data-testid={testId}
      aria-pressed={chosen}
      disabled={disabled}
      onClick={onClick}
      className={cn(
        'w-full rounded border px-3 py-1.5 text-left text-sm',
        chosen ? 'border-primary bg-primary/10 font-medium' : 'border-border hover:bg-muted/50',
        disabled && 'cursor-not-allowed opacity-50'
      )}
    >
      {label}
    </button>
  );
}
