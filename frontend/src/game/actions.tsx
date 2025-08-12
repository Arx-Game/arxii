import { useGameSocket } from '@/hooks/useGameSocket';
import type { CommandSpec } from './types';
import type { LucideIcon } from 'lucide-react';
import { Eye, Hand, MessageCircle } from 'lucide-react';
import type { ComponentType } from 'react';

export interface ActionComponentProps extends CommandSpec {
  character: string;
}

const makeIconAction = (action: string, Icon: LucideIcon): ComponentType<ActionComponentProps> => {
  return function IconAction({ character, command }: ActionComponentProps) {
    const { send } = useGameSocket();
    return (
      <button
        onClick={() => send(character, command)}
        aria-label={action}
        className="rounded p-1 hover:bg-accent"
      >
        <Icon className="h-4 w-4" />
      </button>
    );
  };
};

export const ACTION_COMPONENT_MAP: Record<string, ComponentType<ActionComponentProps>> = {
  look: makeIconAction('look', Eye),
  get: makeIconAction('get', Hand),
  talk: makeIconAction('talk', MessageCircle),
};
