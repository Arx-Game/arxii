import { useEffect, useRef, useCallback } from 'react'
import { useAppDispatch } from '../store/hooks'
import { addMessage, setConnectionStatus } from '../store/gameSlice'

export function useGameSocket() {
  const dispatch = useAppDispatch()
  const socketRef = useRef<WebSocket | null>(null)

  useEffect(() => {
    const protocol = window.location.protocol === 'https:' ? 'wss' : 'ws'
    const socket = new WebSocket(`${protocol}://${window.location.host}/ws/game/`)
    socketRef.current = socket

    socket.addEventListener('open', () => dispatch(setConnectionStatus(true)))
    socket.addEventListener('close', () => dispatch(setConnectionStatus(false)))
    socket.addEventListener('message', (event) => {
      dispatch(
        addMessage({
          content: event.data,
          timestamp: Date.now(),
          type: 'chat',
        })
      )
    })

    return () => {
      socket.close()
      dispatch(setConnectionStatus(false))
    }
  }, [dispatch])

  const send = useCallback((data: string) => {
    const socket = socketRef.current
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(data)
    }
  }, [])

  return { send }
}
