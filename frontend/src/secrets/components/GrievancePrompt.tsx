import { useState } from 'react';

import { useGrievanceOptionsQuery, useSubmitGrievanceMutation } from '../queries';

/** The wronged character's response to a secret about its subject (#1429).
 *
 * Shown on the secret tab only for a secret the viewer is a wronged party to (`can_grieve`). The
 * victim *decides* the effect — a preset swing toward the perpetrator — which the backend applies
 * as a one-sided relationship capstone. Mirrors the telnet `+grievance` command. (A custom-value
 * field is a later follow-up; the API + telnet already accept one.)
 */
export function GrievancePrompt({ secretId, viewerId }: { secretId: number; viewerId: number }) {
  const [open, setOpen] = useState(false);
  const { data: options } = useGrievanceOptionsQuery();
  const submit = useSubmitGrievanceMutation();

  if (submit.isSuccess) {
    return <p className="text-sm italic text-muted-foreground">Your grievance is registered.</p>;
  }

  if (!open) {
    return (
      <button
        type="button"
        className="text-sm font-medium text-primary underline-offset-2 hover:underline"
        onClick={() => setOpen(true)}
      >
        Respond to this wrong…
      </button>
    );
  }

  return (
    <div className="space-y-2 rounded-md border border-dashed p-2">
      <p className="text-sm font-medium">How does this land on your regard for them?</p>
      <div className="flex flex-wrap gap-2">
        {(options ?? []).map((option) => (
          <button
            key={option.id}
            type="button"
            disabled={submit.isPending}
            className="rounded border px-2 py-1 text-sm hover:bg-accent disabled:opacity-50"
            onClick={() => submit.mutate({ secret: secretId, viewer: viewerId, option: option.id })}
          >
            {option.label}
          </button>
        ))}
      </div>
      {submit.isError && (
        <p className="text-sm text-destructive">{(submit.error as Error).message}</p>
      )}
      <button
        type="button"
        className="text-xs text-muted-foreground underline"
        onClick={() => setOpen(false)}
      >
        Cancel
      </button>
    </div>
  );
}
