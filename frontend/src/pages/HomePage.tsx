import { Link } from 'react-router-dom'

export function HomePage() {
  return (
    <div className="mx-auto max-w-2xl text-center">
      <h1 className="mb-6 text-4xl font-bold">Welcome to Arx II</h1>
      <p className="mb-8 text-lg text-muted-foreground">
        A modern MUD experience built with React and Django
      </p>
      <Link
        to="/game"
        className="inline-flex h-10 items-center justify-center rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground ring-offset-background transition-colors hover:bg-primary/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 disabled:pointer-events-none disabled:opacity-50"
      >
        Enter Game
      </Link>
    </div>
  )
}
