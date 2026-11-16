/**
 * The foot of the Lineage stage (#5146): the way back, "Restart: Clear All Choices", the
 * way forward. Restart empties the life (every pick under Life So Far, `useClearLife`)
 * and asks first; it replaces the "Start blank" button that sat under the last grid and
 * cleared on one click.
 */
import { useIsMutating } from '@tanstack/react-query';
import { useState } from 'react';
import { ConfirmDialog, PageTurn } from '../../folio';
import { lifeMutationKey, useClearLife } from '../../queries';
import type { CGExplanations, CharacterDraft } from '../../types';

interface Door {
  label: string;
  onClick: () => void;
}
interface LineagePageTurnProps {
  draft: CharacterDraft;
  copy: CGExplanations | undefined;
  back?: Door;
  next?: Door;
}

export function LineagePageTurn({ draft, copy, back, next }: LineagePageTurnProps) {
  const clearLife = useClearLife(draft.id);
  // A load of the suggested life or a clear already in flight: a second clear would race it.
  const lifeChanging = useIsMutating({ mutationKey: lifeMutationKey(draft.id) }) > 0;
  const [asking, setAsking] = useState(false);
  const label = copy?.life_restart_label ?? 'Restart: Clear All Choices';
  const life = copy?.life_so_far_heading ?? 'Life So Far';
  return (
    <>
      <PageTurn
        back={back}
        between={{ label, onClick: () => setAsking(true), disabled: lifeChanging }}
        next={next}
      />
      <ConfirmDialog
        open={asking}
        title={label}
        confirmLabel={copy?.life_restart_confirm ?? 'Clear all choices'}
        cancelLabel="Cancel"
        onConfirm={() => {
          setAsking(false);
          clearLife.mutate();
        }}
        onCancel={() => setAsking(false)}
      >
        {(
          copy?.life_restart_warning ??
          'This removes every choice under {life}. Your family and the other stages are kept.'
        ).replace('{life}', life)}
      </ConfirmDialog>
    </>
  );
}
