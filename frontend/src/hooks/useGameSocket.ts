import { useAppDispatch } from '../store/hooks';
import { addSessionMessage, setSessionConnectionStatus } from '../store/gameSlice';
import { parseGameMessage } from './parseGameMessage';
import { WS_MESSAGE_TYPE } from './types';
import type { OutgoingMessage } from './types';
import { useCallback } from 'react';

const sockets: Record<string, WebSocket> = {};

export function useGameSocket() {
  const dispatch = useAppDispatch();

  const connect = useCallback(
    (character: string) => {
      if (sockets[character]) return;
      const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
      const socketPort = Number(process.env.WS_PORT) || 4002;
      const socket = new WebSocket(
        `${protocol}://${window.location.hostname}:${socketPort}/ws/game/`
      );
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
    [dispatch]
  );

  const send = useCallback((character: string, command: string) => {
    const socket = sockets[character];
    if (socket && socket.readyState === WebSocket.OPEN) {
      const message: OutgoingMessage = [WS_MESSAGE_TYPE.TEXT, [command], {}];
      socket.send(JSON.stringify(message));
    }
  }, []);

  return { connect, send };
}
