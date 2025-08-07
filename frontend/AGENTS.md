# AGENTS

This directory contains the React frontend. Development is tracked in this file.

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
