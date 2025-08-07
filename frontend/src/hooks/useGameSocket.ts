import { useAppDispatch, useAppSelector } from '../store/hooks';
import { addSessionMessage, setSessionConnectionStatus } from '../store/gameSlice';
import { parseGameMessage } from './parseGameMessage';
import { WS_MESSAGE_TYPE } from './types';
import type { OutgoingMessage } from './types';
import { useCallback } from 'react';

const sockets: Record<string, WebSocket> = {};

export function useGameSocket() {
  const dispatch = useAppDispatch();
  const account = useAppSelector((state) => state.auth.account);

  const connect = useCallback(
    async (character: string) => {
      if (sockets[character]) return;

      // Check if user is authenticated and has session_key
      if (!account?.session_key) {
        console.error('No session key available for websocket authentication');
        return;
      }

      const sessionId = account.session_key;

      const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
      const socketPort = Number(process.env.WS_PORT) || 4002;

      // Generate client UID (similar to Evennia's generateUID function)
      const generateUID = () =>
        Math.random().toString(36).substring(2, 15) + Math.random().toString(36).substring(2, 15);
      const clientUID = generateUID();
      const browser = navigator.userAgent;

      const url = sessionId
        ? `${protocol}://${window.location.hostname}:${socketPort}/ws/game/?${sessionId}&${clientUID}&${encodeURIComponent(browser)}`
        : `${protocol}://${window.location.hostname}:${socketPort}/ws/game/`;

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
    [dispatch, account?.session_key]
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
