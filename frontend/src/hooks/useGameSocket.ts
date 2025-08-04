import { useEffect, useRef, useCallback } from 'react';
import { useAppDispatch } from '../store/hooks';
import { addMessage, setConnectionStatus } from '../store/gameSlice';

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
      try {
        const data = JSON.parse(event.data);
        if (Array.isArray(data) && data.length >= 2) {
          const [msgType, args, kwargs = {}] = data;

          // Extract the actual message content based on message type
          let content = '';
          let messageType: 'system' | 'chat' | 'action' | 'text' | 'channel' | 'error' = 'system';

          if (msgType === 'text' && Array.isArray(args) && args.length > 0) {
            content = args[0];
            messageType = kwargs.from_channel ? 'channel' : 'text';
          } else if (msgType === 'logged_in') {
            content = 'Successfully logged in!';
            messageType = 'system';
          } else {
            // For other message types, show the raw content for now
            content = JSON.stringify(data);
            messageType = 'system';
          }

          dispatch(
            addMessage({
              content,
              timestamp: Date.now(),
              type: messageType,
            })
          );
        }
      } catch (error) {
        console.error('Failed to parse websocket message:', error);
        // Fallback to raw display
        dispatch(
          addMessage({
            content: event.data,
            timestamp: Date.now(),
            type: 'error',
          })
        );
      }
    });

    return () => {
      socket.close();
      dispatch(setConnectionStatus(false));
    };
  }, [dispatch]);

  const send = useCallback((command: string) => {
    const socket = socketRef.current;
    if (socket && socket.readyState === WebSocket.OPEN) {
      // Format as Evennia expects: ["inputfunc", [args], {kwargs}]
      const message = ['text', [command], {}];
      socket.send(JSON.stringify(message));
    }
  }, []);

  return { send };
}
