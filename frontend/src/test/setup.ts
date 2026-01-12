import '@testing-library/jest-dom';
import { vi } from 'vitest';
import React from 'react';

// Mock framer-motion to disable animations in tests
vi.mock('framer-motion', async () => {
  const actual = await vi.importActual('framer-motion');

  // Filter out motion-specific props
  const filterProps = (props: Record<string, unknown>) => {
    // eslint-disable-next-line @typescript-eslint/no-unused-vars
    const { initial, animate, exit, transition, variants, whileHover, whileTap, ...rest } = props;
    return rest;
  };

  type MotionComponentProps = {
    children?: React.ReactNode;
  } & Record<string, unknown>;

  return {
    ...actual,
    motion: {
      div: ({ children, ...props }: MotionComponentProps) =>
        React.createElement('div', filterProps(props), children),
      span: ({ children, ...props }: MotionComponentProps) =>
        React.createElement('span', filterProps(props), children),
      button: ({ children, ...props }: MotionComponentProps) =>
        React.createElement('button', filterProps(props), children),
    },
  };
});

// Add Vitest global types
declare global {
  const describe: typeof import('vitest').describe;
  const it: typeof import('vitest').it;
  const test: typeof import('vitest').test;
  const expect: typeof import('vitest').expect;
  const beforeAll: typeof import('vitest').beforeAll;
  const afterAll: typeof import('vitest').afterAll;
  const beforeEach: typeof import('vitest').beforeEach;
  const afterEach: typeof import('vitest').afterEach;
  const vi: typeof import('vitest').vi;
}
