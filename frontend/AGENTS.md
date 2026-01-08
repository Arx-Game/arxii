# AGENTS

This directory contains the React frontend. Development is tracked in this file.

## Important: Git Commands

**Never** use git commands that open a pager (vim/less) - this causes agents to hang indefinitely:

```bash
# BAD - opens pager, agent gets stuck
git diff
git log
git show
git diff --no-pager  # --no-pager is not a valid git option

# GOOD - pipe to cat to bypass pager
git diff | cat
git log | cat
git show | cat
```

## Plan

- Use Vite with React and TypeScript.
- Handle routing with React Router.
- Fetch data through React Query hitting the Django REST API.
- Use Redux Toolkit for shared state and websocket integration.
- Style components with shadcn/ui and Tailwind CSS.
- Prefer using existing components from shadcn/ui and avoid creating custom equivalents when a shadcn component exists.

## Progress

- Docs directory created with initial architecture notes.
- Configuration of Node and pnpm managed via `mise`.
- Basic GamePage wired to Redux with a websocket hook.
- Game client components extracted into dedicated directory.
- Initial handler added for websocket `commands` messages to prepare for
  frontend state updates.
