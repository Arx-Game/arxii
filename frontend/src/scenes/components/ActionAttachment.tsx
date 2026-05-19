import { useState, useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { Zap, X, Loader2 } from 'lucide-react';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { useAppSelector } from '@/store/hooks';
import { useMyRosterEntriesQuery } from '@/roster/queries';
import { fetchAvailableActions } from '../actionQueries';
import type { ActionAttachmentInfo, PlayerAction } from '../actionTypes';

interface ActionAttachmentProps {
  sceneId: string;
  attachment: ActionAttachmentInfo | null;
  onAttach: (action: ActionAttachmentInfo) => void;
  onDetach: () => void;
  targetName?: string;
}

export function ActionAttachment({
  sceneId: _sceneId,
  attachment,
  onAttach,
  onDetach,
  targetName,
}: ActionAttachmentProps) {
  const [open, setOpen] = useState(false);

  // Resolve active character to numeric ObjectDB pk — same pattern as FocusPanel.
  const activeCharacterName = useAppSelector((state) => state.game.active);
  const { data: myRosterEntries = [] } = useMyRosterEntriesQuery();
  const characterId = useMemo(
    () => myRosterEntries.find((e) => e.name === activeCharacterName)?.character_id ?? null,
    [myRosterEntries, activeCharacterName]
  );

  const { data, isLoading } = useQuery({
    queryKey: ['available-actions', characterId],
    queryFn: () => fetchAvailableActions(characterId!),
    enabled: open && characterId !== null,
    staleTime: 30_000,
  });

  function handleSelect(action: PlayerAction, isTargeted: boolean) {
    const techniqueId = action.ref.technique_id ?? undefined;
    const actionKey =
      action.ref.registry_key ??
      action.action_template?.name.toLowerCase() ??
      action.display_name.toLowerCase();
    onAttach({
      actionKey,
      name: action.display_name,
      target: isTargeted ? targetName : undefined,
      requiresTarget: isTargeted,
      techniqueId,
    });
    setOpen(false);
  }

  const availableActions: { action: PlayerAction; targeted: boolean }[] = (data?.results ?? [])
    .filter((a) => a.prerequisite_met)
    .map((a) => ({ action: a, targeted: false }));
  const hasActions = availableActions.length > 0;

  return (
    <div className="flex items-center gap-1">
      <Popover open={open} onOpenChange={setOpen}>
        <PopoverTrigger asChild>
          <button
            type="button"
            aria-label="Attach action"
            title={attachment ? 'Click to detach action' : 'Attach action'}
            className={`flex h-6 w-6 items-center justify-center rounded text-xs hover:bg-accent hover:text-accent-foreground ${
              attachment ? 'bg-accent text-accent-foreground' : ''
            }`}
            onClick={(e) => {
              if (attachment) {
                e.preventDefault();
                onDetach();
              }
            }}
          >
            <Zap className="h-3.5 w-3.5" />
          </button>
        </PopoverTrigger>
        <PopoverContent side="top" align="start" className="w-56 p-2">
          {isLoading && (
            <div className="flex items-center gap-2 p-2 text-sm text-muted-foreground">
              <Loader2 className="h-3.5 w-3.5 animate-spin" />
              Loading...
            </div>
          )}
          {data && !hasActions && (
            <p className="p-2 text-sm text-muted-foreground">No actions available</p>
          )}
          {data && hasActions && (
            <div className="space-y-1">
              {availableActions.map(({ action, targeted }) => (
                <button
                  key={`${action.ref.backend}-${action.ref.challenge_instance_id ?? ''}-${action.ref.approach_id ?? ''}-${action.ref.registry_key ?? ''}`}
                  type="button"
                  className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-sm hover:bg-accent hover:text-accent-foreground"
                  onClick={() => handleSelect(action, targeted)}
                >
                  <Zap className="h-3.5 w-3.5 shrink-0" />
                  <span>{action.display_name}</span>
                  {targeted && (
                    <span className="ml-auto text-xs text-muted-foreground">targeted</span>
                  )}
                </button>
              ))}
            </div>
          )}
        </PopoverContent>
      </Popover>

      {attachment && (
        <button
          type="button"
          aria-label="Detach action"
          onClick={onDetach}
          className="flex items-center gap-1 rounded-full bg-accent px-2 py-0.5 text-xs text-accent-foreground hover:bg-accent/80"
        >
          <Zap className="h-3 w-3" />
          {attachment.name}
          {attachment.requiresTarget && (
            <span className="text-muted-foreground">
              {attachment.target ? `\u2192 ${attachment.target}` : '(select target)'}
            </span>
          )}
          <X className="ml-1 h-3 w-3" />
        </button>
      )}
    </div>
  );
}
