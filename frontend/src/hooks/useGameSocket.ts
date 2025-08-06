import { useEffect, useRef, useCallback } from 'react';
import { useAppDispatch } from '../store/hooks';
import { addMessage, setConnectionStatus } from '../store/gameSlice';
import { parseGameMessage } from './parseGameMessage';
import { WS_MESSAGE_TYPE } from './types';
import type { OutgoingMessage } from './types';

let socket: WebSocket | null = null;
let listenersAttached = false;

export function useGameSocket() {
  const dispatch = useAppDispatch();
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!socket) {
      const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
      const socketPort = process.env.WS_PORT || 4002;
      socket = new WebSocket(`${protocol}://${window.location.hostname}:${socketPort}/ws/game/`);
    }
    socketRef.current = socket;

    if (!listenersAttached && socket) {
      socket.addEventListener('open', () => dispatch(setConnectionStatus(true)));
      socket.addEventListener('close', () => dispatch(setConnectionStatus(false)));
      socket.addEventListener('message', (event) => {
        const message = parseGameMessage(event.data);
        dispatch(addMessage(message));
      });
      listenersAttached = true;
    }
  }, [dispatch]);

  const send = useCallback((command: string) => {
    const current = socketRef.current;
    if (current && current.readyState === WebSocket.OPEN) {
      const message: OutgoingMessage = [WS_MESSAGE_TYPE.TEXT, [command], {}];
      current.send(JSON.stringify(message));
    }
  }, []);

  return { send };
}
