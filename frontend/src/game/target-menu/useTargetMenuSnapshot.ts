import { useEffect, useMemo, useRef, useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  fetchTargetMenu,
  targetMenuInputPageKey,
  targetMenuQueryPolicy,
  type TargetMenuData,
  type TargetMenuTarget,
} from './targetMenuApi';

interface SnapshotState {
  identity: string;
  data: TargetMenuData | null;
  error: unknown;
  loading: boolean;
}

export function useTargetMenuSnapshot(
  partition: string,
  actorId: number | null,
  target: TargetMenuTarget,
  open: boolean,
  inputsFor?: string,
  candidateCursor?: string
) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<SnapshotState>({
    identity: '',
    data: null,
    error: null,
    loading: false,
  });
  const generation = useRef(0);
  const stableTarget = useMemo(
    () => ({
      kind: target.kind,
      target_id: target.target_id,
      ...(target.owner_persona_id === undefined
        ? {}
        : { owner_persona_id: target.owner_persona_id }),
      ...(target.container_item_id === undefined
        ? {}
        : { container_item_id: target.container_item_id }),
    }),
    [target.container_item_id, target.kind, target.owner_persona_id, target.target_id]
  );
  const identity = useMemo(
    () =>
      actorId === null || partition.length === 0
        ? ''
        : JSON.stringify(
            targetMenuInputPageKey(
              partition,
              actorId,
              stableTarget,
              inputsFor ?? '',
              candidateCursor
            )
          ),
    [actorId, candidateCursor, inputsFor, partition, stableTarget]
  );

  useEffect(() => {
    const requestGeneration = ++generation.current;
    if (!open || identity.length === 0 || actorId === null) {
      setState({ identity, data: null, error: null, loading: false });
      return;
    }

    setState({ identity, data: null, error: null, loading: true });
    void queryClient
      .fetchQuery({
        queryKey: targetMenuInputPageKey(
          partition,
          actorId,
          stableTarget,
          inputsFor ?? '',
          candidateCursor
        ),
        queryFn: ({ signal }) =>
          fetchTargetMenu(actorId, stableTarget, signal, inputsFor, candidateCursor),
        ...targetMenuQueryPolicy,
      })
      .then((data) => {
        if (generation.current !== requestGeneration) return;
        setState({ identity, data, error: null, loading: false });
      })
      .catch((error: unknown) => {
        if (generation.current !== requestGeneration) return;
        setState({ identity, data: null, error, loading: false });
      });

    return () => {
      if (generation.current === requestGeneration) generation.current += 1;
    };
  }, [actorId, candidateCursor, identity, inputsFor, open, partition, queryClient, stableTarget]);

  const current = state.identity === identity;
  return {
    data: open && current ? state.data : null,
    error: open && current ? state.error : null,
    isLoading: open && identity.length > 0 && (!current || state.loading),
  };
}
