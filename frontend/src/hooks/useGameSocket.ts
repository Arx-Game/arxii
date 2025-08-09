import { useAppDispatch, useAppSelector } from '../store/hooks';
import { addSessionMessage, setSessionConnectionStatus } from '../store/gameSlice';
import { parseGameMessage } from './parseGameMessage';
import { WS_MESSAGE_TYPE } from './types';
import type { OutgoingMessage } from './types';
import { useCallback } from 'react';
import type { MyRosterEntry } from '../roster/types';
import { WS_PORT } from '../config';

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
        const message = parseGameMessage(event.data);
        dispatch(addSessionMessage({ character, message }));
      });
    },
    [dispatch, account]
  );

  const send = useCallback((character: MyRosterEntry['name'], command: string) => {
    const socket = sockets[character];
    if (socket && socket.readyState === WebSocket.OPEN) {
      const message: OutgoingMessage = [WS_MESSAGE_TYPE.TEXT, [command], {}];
      socket.send(JSON.stringify(message));
    }
  }, []);

  return { connect, send };
}
