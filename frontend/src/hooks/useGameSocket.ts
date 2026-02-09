import { useAppDispatch, useAppSelector } from '@/store/hooks';
import { addSessionMessage, resetGame, setSessionConnectionStatus } from '@/store/gameSlice';
import { setAccount } from '@/store/authSlice';
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
import { handleRoulettePayload } from './handleRoulettePayload';
import type { RoulettePayload } from '@/components/roulette/types';

import { useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import type { MyRosterEntry } from '@/roster/types';
import { WS_PORT } from '@/config';
import { toast } from 'sonner';
import { fetchAccount } from '@/evennia_replacements/api';

const sockets: Record<string, WebSocket> = {};

export function useGameSocket() {
  const dispatch = useAppDispatch();
  const account = useAppSelector((state) => state.auth.account);
  const navigate = useNavigate();

  const disconnectAll = useCallback(() => {
    Object.values(sockets).forEach((socket) => socket.close());
  }, []);

  const connect = useCallback(
    async (character: MyRosterEntry['name']) => {
      if (sockets[character]) return;

      let currentAccount = account;
      if (!currentAccount) {
        try {
          currentAccount = await fetchAccount();
          if (currentAccount) {
            dispatch(setAccount(currentAccount));
          } else {
            navigate('/login');
            return;
          }
        } catch {
          navigate('/login');
          return;
        }
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

      socket.addEventListener('close', (event) => {
        dispatch(setSessionConnectionStatus({ character, status: false }));
        delete sockets[character];
        if (event.code === 1000) {
          // Only reset game state if this was the last active connection
          const remainingConnections = Object.keys(sockets).length;
          if (remainingConnections === 0) {
            dispatch(resetGame());
          }
        }
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

          if (msgType === WS_MESSAGE_TYPE.ROULETTE_RESULT) {
            handleRoulettePayload(kwargs as unknown as RoulettePayload, dispatch);
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
    [account, dispatch, navigate]
  );

  const send = useCallback((character: MyRosterEntry['name'], command: string) => {
    const socket = sockets[character];
    if (socket && socket.readyState === WebSocket.OPEN) {
      const message: OutgoingMessage = [WS_MESSAGE_TYPE.TEXT, [command], {}];
      socket.send(JSON.stringify(message));
    }
  }, []);

  return { connect, send, disconnectAll };
}
