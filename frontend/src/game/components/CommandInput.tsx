import { useState } from 'react'
import { useGameSocket } from '../../hooks/useGameSocket'

export function CommandInput() {
  const [command, setCommand] = useState('')
  const { send } = useGameSocket()

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    const trimmed = command.trim()
    if (trimmed) {
      send(trimmed)
      setCommand('')
    }
  }

  return (
    <form onSubmit={handleSubmit}>
      <input
        type="text"
        placeholder="Enter command..."
        value={command}
        onChange={(e) => setCommand(e.target.value)}
        className="w-full rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background file:border-0 file:bg-transparent file:text-sm file:font-medium placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:cursor-not-allowed disabled:opacity-50"
      />
    </form>
  )
}
