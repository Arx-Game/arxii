/**
 * TemplateRuleSection — edit the template's availability_rule predicate.
 *
 * Lives inside MissionDetailPanel below the template metadata. Uses
 * the same useServerDraft + validate-before-save + coerce-on-save
 * machinery as OptionPage's visibility_rule editor.
 */

import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';

import { patchMissionTemplate } from '../api';
import {
  coercePredicate,
  PredicateBuilder,
  validatePredicate,
  type PredicateNode,
} from './PredicateBuilder';
import { ServerChangedBanner } from './ServerChangedBanner';
import { useServerDraft } from '../hooks/useServerDraft';
import { missionKeys, usePredicateLeaves } from '../queries';
import type { MissionTemplate } from '../types';
import { useMutation, useQueryClient } from '@tanstack/react-query';

interface Props {
  template: MissionTemplate;
}

export function TemplateRuleSection({ template }: Props) {
  const qc = useQueryClient();
  const leaves = usePredicateLeaves();
  const { draft, setDraft, dirty, serverChanged, pullFromServer } = useServerDraft(
    template,
    (t) => ({
      availability_rule: (t.availability_rule ?? {}) as PredicateNode,
    })
  );
  const ruleErrors = validatePredicate(draft.availability_rule, leaves.data ?? []);
  const ruleValid = ruleErrors.length === 0;

  const mutation = useMutation({
    mutationFn: () =>
      patchMissionTemplate(template.id, {
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        availability_rule: coercePredicate(draft.availability_rule, leaves.data ?? []) as any,
      }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: missionKeys.templateDetail(template.id) });
      qc.invalidateQueries({ queryKey: missionKeys.templates() });
    },
  });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-base">Availability rule</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3" data-testid="template-rule-section">
        {serverChanged ? <ServerChangedBanner onPull={pullFromServer} /> : null}
        <PredicateBuilder
          value={draft.availability_rule}
          onChange={(next) => setDraft({ availability_rule: next })}
        />
        {!ruleValid && dirty ? (
          <div className="rounded border border-destructive/60 bg-destructive/10 px-3 py-2 text-sm text-destructive">
            <div className="font-medium">Availability rule is not safe to save:</div>
            <ul className="list-inside list-disc">
              {ruleErrors.map((err) => (
                <li key={err}>{err}</li>
              ))}
            </ul>
          </div>
        ) : null}
        {mutation.error ? (
          <div className="text-sm text-destructive">{String(mutation.error.message)}</div>
        ) : null}
        <div className="flex justify-end">
          <Button
            size="sm"
            onClick={() => mutation.mutate()}
            disabled={!dirty || !ruleValid || mutation.isPending}
          >
            {mutation.isPending ? 'Saving…' : 'Save rule'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}
