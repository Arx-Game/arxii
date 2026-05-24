import { useState, useCallback, useEffect, useMemo, useRef } from 'react';
import { useGameSocket } from '@/hooks/useGameSocket';
import { RichTextInput } from '@/components/RichTextInput';
import { ModeSelector } from '@/scenes/components/ModeSelector';
import { ActionAttachment } from '@/scenes/components/ActionAttachment';
import { useAppSelector } from '@/store/hooks';
import type { MyRosterEntry } from '@/roster/types';
import type { ActionAttachmentInfo } from '@/scenes/actionTypes';
import { submitPose } from '@/scenes/queries';

export interface ComposerMode {
  command: string; // "pose" | "say" | "tt" | "whisper"
  targets: string[]; // persona names for @targeting
  label: string; // "Pose -> The Grand Ballroom"
}

const KNOWN_COMMANDS = ['pose', 'say', 'emit', 'emote', 'whisper', 'tt', 'tabletalk'];

interface CommandInputProps {
  character: MyRosterEntry['name'];
  composerMode?: ComposerMode;
  onModeChange?: (mode: ComposerMode) => void;
  targetToAppend?: string | null;
  onTargetConsumed?: () => void;
  sceneId?: string;
  actionAttachment?: ActionAttachmentInfo | null;
  onActionAttach?: (action: ActionAttachmentInfo) => void;
  onActionDetach?: () => void;
  onSubmitAction?: (action: ActionAttachmentInfo) => void;
  /** Persona id for the active character — used to call submit_pose REST endpoint. */
  personaId?: number | null;
  /** IDs of the persona's unlinked ACTION interactions in this scene (from usePendingUnlinkedActions). */
  pendingActionIds?: number[];
  /** IDs the user has explicitly detached — these will be omitted from action_link_ids. */
  detachedActionIds?: number[];
  /** Called after a successful pose submit so the parent can clear detachedActionIds. */
  onPoseSubmitted?: () => void;
}

export function CommandInput({
  character,
  composerMode,
  onModeChange,
  targetToAppend,
  onTargetConsumed,
  sceneId,
  actionAttachment,
  onActionAttach,
  onActionDetach,
  onSubmitAction,
  personaId,
  pendingActionIds,
  detachedActionIds,
  onPoseSubmitted,
}: CommandInputProps) {
  const [command, setCommand] = useState('');
  const [history, setHistory] = useState<string[]>([]);
  const [historyIndex, setHistoryIndex] = useState<number>(-1);
  const submittingRef = useRef(false);
  const { send } = useGameSocket();

  const activeCharacter = useAppSelector((state) => state.game.active);
  const roomCharacters = useAppSelector((state) => {
    if (!activeCharacter) return [];
    const room = state.game.sessions[activeCharacter]?.room;
    return room?.characters ?? [];
  });

  const handleSubmit = useCallback(() => {
    if (submittingRef.current) return;
    const trimmed = command.trim();
    if (!trimmed) return;

    // I4: Whisper mode requires a target — don't send a malformed command
    if (composerMode?.command === 'whisper' && composerMode.targets.length === 0) {
      return;
    }

    submittingRef.current = true;

    let fullCommand = trimmed;
    if (composerMode) {
      const firstWord = trimmed.split(' ')[0].toLowerCase();
      const hasExplicitCommand = KNOWN_COMMANDS.includes(firstWord);

      if (!hasExplicitCommand) {
        if (composerMode.command === 'whisper' && composerMode.targets.length > 0) {
          fullCommand = `whisper ${composerMode.targets[0]}=${trimmed}`;
        } else {
          const targetStr =
            composerMode.targets.length > 0 ? ` @${composerMode.targets.join(',@')} ` : ' ';
          fullCommand = `${composerMode.command}${targetStr}${trimmed}`;
        }
      }
    }

    // C2: Pose (WebSocket) and action (REST) are submitted independently.
    // Both are fire-and-forget — there is no transactional link between them.
    // The SceneActionRequest has a `scene` FK so they are contextually linked,
    // but if one fails the other may still succeed.
    send(character, fullCommand);

    if (actionAttachment && onSubmitAction) {
      onSubmitAction(actionAttachment);
    }

    // When posing in a scene with a known persona, call the submit_pose REST
    // endpoint to associate pending ACTION interactions via auto-link (or
    // explicit detach override).  This is fire-and-forget alongside the
    // WebSocket send — the backend deduplicates via the auto-link service.
    const isPose = !composerMode || composerMode.command === 'pose';
    if (isPose && sceneId && personaId != null) {
      const detachedSet = new Set(detachedActionIds ?? []);
      const hasPending = (pendingActionIds ?? []).length > 0;
      const hasDetachments = detachedSet.size > 0;

      // Only send action_link_ids when the user detached something — otherwise
      // omit the field so server-side auto-link runs (no redundant override).
      const body =
        hasPending && hasDetachments
          ? {
              persona_id: personaId,
              scene_id: Number(sceneId),
              content: trimmed,
              action_link_ids: (pendingActionIds ?? []).filter((id) => !detachedSet.has(id)),
            }
          : { persona_id: personaId, scene_id: Number(sceneId), content: trimmed };

      void submitPose(body).then(() => {
        onPoseSubmitted?.();
      });
    }

    setHistory((prev) => [...prev, trimmed]);
    setHistoryIndex(-1);
    setCommand('');
    // I3: Clear synchronously — React batches the state updates above,
    // so this runs on the same tick and prevents double-submission.
    submittingRef.current = false;
  }, [
    character,
    command,
    composerMode,
    send,
    actionAttachment,
    onSubmitAction,
    sceneId,
    personaId,
    pendingActionIds,
    detachedActionIds,
    onPoseSubmitted,
  ]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'ArrowUp' && command === '') {
      e.preventDefault();
      if (history.length > 0) {
        const newIndex = historyIndex <= 0 ? history.length - 1 : historyIndex - 1;
        setHistoryIndex(newIndex);
        setCommand(history[newIndex]);
      }
    }
  };

  const handleModeChange = useCallback(
    (mode: string) => {
      if (onModeChange && composerMode) {
        const label = mode.charAt(0).toUpperCase() + mode.slice(1);
        onModeChange({
          command: mode,
          targets: composerMode.targets,
          label,
        });
      }
    },
    [onModeChange, composerMode]
  );

  const handleChange = useCallback((val: string) => {
    setCommand(val);
    setHistoryIndex(-1);
  }, []);

  const ghostText = useMemo(() => {
    if (!composerMode) return '';
    const mode = composerMode.command.charAt(0).toUpperCase() + composerMode.command.slice(1);
    let text: string;
    if (composerMode.targets.length > 0) {
      text = `${mode} \u2192 ${composerMode.targets.join(', ')}`;
    } else {
      text = composerMode.label || mode;
    }
    if (actionAttachment) {
      text += ` | \u2694 ${actionAttachment.name}`;
      if (actionAttachment.target) text += ` \u2192 ${actionAttachment.target}`;
    }
    return text;
  }, [composerMode, actionAttachment]);

  // Append @name when a pending target arrives
  useEffect(() => {
    if (targetToAppend) {
      setCommand((prev) => {
        const prefix = prev.trim() ? prev + ' ' : '';
        return `${prefix}@${targetToAppend}`;
      });
      onTargetConsumed?.();
    }
  }, [targetToAppend, onTargetConsumed]);

  return (
    <div className="shrink-0 border-t">
      <RichTextInput
        value={command}
        onChange={handleChange}
        onSubmit={handleSubmit}
        onKeyDown={handleKeyDown}
        rows={2}
        leftSlot={
          <ModeSelector
            currentMode={composerMode?.command ?? 'pose'}
            onModeChange={handleModeChange}
            // TODO: derive from PlacePresence when place system is integrated
            isAtPlace={false}
          />
        }
        rightSlot={
          sceneId ? (
            <ActionAttachment
              sceneId={sceneId}
              attachment={actionAttachment ?? null}
              onAttach={(action) => onActionAttach?.(action)}
              onDetach={() => onActionDetach?.()}
              targetName={composerMode?.targets[0]}
            />
          ) : undefined
        }
        ghostText={ghostText}
        autocompleteItems={roomCharacters}
      />
    </div>
  );
}
