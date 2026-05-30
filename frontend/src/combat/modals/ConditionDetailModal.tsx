/**
 * ConditionDetailModal — inner content for the `condition` deep link (#551).
 *
 * Renders ONLY the inner modal content (DialogHeader/DialogTitle + body). The
 * DeepLinkModalHost owns the Dialog + DialogContent wrapper, so every kind's
 * content shares one consistent dialog frame.
 *
 * Data source: useConditionInstance(id) → ConditionInstance serializer.
 */

import { DialogDescription, DialogHeader, DialogTitle } from '@/components/ui/dialog';
import { useConditionInstance } from '@/conditions/queries';

export interface ConditionDetailModalProps {
  id: number;
}

export function ConditionDetailModal({ id }: ConditionDetailModalProps) {
  const { data: condition, isLoading, isError } = useConditionInstance(id);

  if (isLoading) {
    return (
      <DialogHeader>
        <DialogTitle>Condition</DialogTitle>
        <DialogDescription data-testid="condition-modal-loading">Loading…</DialogDescription>
      </DialogHeader>
    );
  }

  if (isError || !condition) {
    return (
      <DialogHeader>
        <DialogTitle>Condition</DialogTitle>
        <DialogDescription data-testid="condition-modal-error">
          Failed to load condition.
        </DialogDescription>
      </DialogHeader>
    );
  }

  return (
    <>
      <DialogHeader>
        <DialogTitle>{condition.name}</DialogTitle>
        {condition.stage_name && (
          <DialogDescription data-testid="condition-modal-stage">
            Stage: {condition.stage_name}
          </DialogDescription>
        )}
      </DialogHeader>

      <div className="space-y-2 text-sm" data-testid="condition-modal-body">
        <p className="text-muted-foreground">{condition.description}</p>
        <dl className="grid grid-cols-2 gap-1 text-xs">
          <dt className="text-muted-foreground">Severity</dt>
          <dd className="text-right font-mono">{condition.severity}</dd>
          {condition.stacks > 1 && (
            <>
              <dt className="text-muted-foreground">Stacks</dt>
              <dd className="text-right font-mono">
                {condition.stacks}
                {condition.max_stacks ? ` / ${condition.max_stacks}` : ''}
              </dd>
            </>
          )}
        </dl>
      </div>
    </>
  );
}
