import { useEffect, useRef, useCallback } from 'react';
import { useAppDispatch } from '../store/hooks';
import { addMessage, setConnectionStatus } from '../store/gameSlice';
import { parseGameMessage } from './parseGameMessage';
import { WS_MESSAGE_TYPE } from './types';
import type { OutgoingMessage } from './types';

export function useGameSocket() {
  const dispatch = useAppDispatch();
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    const socketPort = process.env.WS_PORT || 4002;
    const socket = new WebSocket(
      `${protocol}://${window.location.hostname}:${socketPort}/ws/game/`
    );
    socketRef.current = socket;

    socket.addEventListener('open', () => dispatch(setConnectionStatus(true)));
    socket.addEventListener('close', () => dispatch(setConnectionStatus(false)));
    socket.addEventListener('message', (event) => {
      const message = parseGameMessage(event.data);
      dispatch(addMessage(message));
    });

    return () => {
      socket.close();
      dispatch(setConnectionStatus(false));
    };
  }, [dispatch]);

  const send = useCallback((command: string) => {
    const socket = socketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) {
      const message: OutgoingMessage = [WS_MESSAGE_TYPE.TEXT, [command], {}];
      socket.send(JSON.stringify(message));
    }
  }, []);

  return { send };
}
