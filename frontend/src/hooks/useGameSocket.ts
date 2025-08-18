import { useAppDispatch, useAppSelector } from '@/store/hooks';
import { addSessionMessage, resetGame, setSessionConnectionStatus } from '@/store/gameSlice';
import { parseGameMessage } from './parseGameMessage';
import { GAME_MESSAGE_TYPE, WS_MESSAGE_TYPE } from './types';

import type {
  CommandErrorPayload,
  GameMessage,
  IncomingMessage,
  OutgoingMessage,
  RoomStatePayload,
  ScenePayload,
} from './types';
import type { CommandSpec } from '@/game/types';
import { handleRoomStatePayload } from './handleRoomStatePayload';
import { handleScenePayload } from './handleScenePayload';
import { handleCommandPayload } from './handleCommandPayload';

import { useCallback } from 'react';
import type { MyRosterEntry } from '@/roster/types';
import { WS_PORT } from '@/config';
import { toast } from 'sonner';

const sockets: Record<string, WebSocket> = {};

export function useGameSocket() {
  const dispatch = useAppDispatch();
  const account = useAppSelector((state) => state.auth.account);

  const connect = useCallback(
    (character: MyRosterEntry['name']) => {
      if (sockets[character]) return;

      // Check if user is authenticated
      if (!account) {
        console.error('User not authenticated for websocket connection');
        return;
      }

      const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
      const socketPort = WS_PORT;

      // Clean websocket URL - middleware will inject session auth from cookies
      const url = `${protocol}://${window.location.hostname}:${socketPort}/ws/game/`;
      const socket = new WebSocket(url);
      sockets[character] = socket;

      socket.addEventListener('open', () => {
        dispatch(setSessionConnectionStatus({ character, status: true }));
        const puppet: OutgoingMessage = [WS_MESSAGE_TYPE.TEXT, [`@ic ${character}`], {}];
        socket.send(JSON.stringify(puppet));
      });

      socket.addEventListener('close', () => {
        dispatch(setSessionConnectionStatus({ character, status: false }));
        delete sockets[character];
      });

      socket.addEventListener('message', (event) => {
        let parsed: unknown;

        try {
          parsed = JSON.parse(event.data);
        } catch {
          // Bad JSON frame: surface as a system message and bail.
          const fallback = {
            content: String(event.data),
            timestamp: Date.now(),
            type: GAME_MESSAGE_TYPE.SYSTEM,
          } as GameMessage;
          dispatch(addSessionMessage({ character, message: fallback }));
          return;
        }

        if (Array.isArray(parsed) && parsed.length >= 2) {
          const [msgType, args, kwargs] = parsed as IncomingMessage;

          // Control message: ROOM_STATE
          if (msgType === WS_MESSAGE_TYPE.ROOM_STATE) {
            handleRoomStatePayload(character, kwargs as unknown as RoomStatePayload, dispatch);
            return;
          }

          if (msgType === WS_MESSAGE_TYPE.SCENE) {
            handleScenePayload(character, kwargs as unknown as ScenePayload, dispatch);
            return;
          }

          if (msgType === WS_MESSAGE_TYPE.COMMAND_ERROR) {
            const { error, command } = (kwargs as unknown as CommandErrorPayload) ?? {};
            toast.error(error, { description: command });
            return;
          }

          // Control message: COMMANDS
          if (msgType === WS_MESSAGE_TYPE.COMMANDS) {
            handleCommandPayload(character, args as CommandSpec[]);
            return;
          }

          // Regular game message
          const message = parseGameMessage(parsed as IncomingMessage);
          dispatch(addSessionMessage({ character, message }));
          return;
        }

        // Unexpected structure: stringify and show
        const fallback = {
          content: JSON.stringify(parsed),
          timestamp: Date.now(),
          type: GAME_MESSAGE_TYPE.SYSTEM,
        } as GameMessage;
        dispatch(addSessionMessage({ character, message: fallback }));
      });
    },
    [dispatch, account]
  );

  const disconnectAll = useCallback(() => {
    Object.values(sockets).forEach((socket) => socket.close());
  }, []);

  const send = useCallback(
    (character: MyRosterEntry['name'], command: string) => {
      const socket = sockets[character];
      if (socket && socket.readyState === WebSocket.OPEN) {
        const message: OutgoingMessage = [WS_MESSAGE_TYPE.TEXT, [command], {}];
        socket.send(JSON.stringify(message));

        if (command.trim().toLowerCase() === 'quit') {
          disconnectAll();
          dispatch(resetGame());
        }
      }
    },
    [disconnectAll, dispatch]
  );

  return { connect, send, disconnectAll };
}
