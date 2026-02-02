#!/usr/bin/env node

import { Server } from "@modelcontextprotocol/sdk/server/index.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import {
  CallToolRequestSchema,
  ListToolsRequestSchema,
} from "@modelcontextprotocol/sdk/types.js";
import { chromium, Browser, BrowserContext, Page, ConsoleMessage } from "playwright";

// Configuration
const BASE_URL = process.env.FRONTEND_BASE_URL || "http://localhost:5173";
const TEST_USERNAME = process.env.TEST_USERNAME || "";
const TEST_PASSWORD = process.env.TEST_PASSWORD || "";

// Browser state
let browser: Browser | null = null;
let context: BrowserContext | null = null;
let page: Page | null = null;

// Tracking for anti-churn safeguards
interface ActionRecord {
  action: string;
  url?: string;
  selector?: string;
  timestamp: number;
}

const recentActions: ActionRecord[] = [];
const MAX_ACTIONS = 10;

// Console and network error tracking
interface TrackedError {
  message: string;
  count: number;
  firstSeen: number;
  lastSeen: number;
}

const consoleErrors: Map<string, TrackedError> = new Map();
const networkErrors: Map<string, TrackedError & { status: number; url: string }> = new Map();

function trackAction(action: string, url?: string, selector?: string) {
  recentActions.push({ action, url, selector, timestamp: Date.now() });
  if (recentActions.length > MAX_ACTIONS) {
    recentActions.shift();
  }
}

function checkForChurn(action: string, url?: string): string | null {
  const similarActions = recentActions.filter(
    (a) => a.action === action && a.url === url
  );

  if (similarActions.length >= 3) {
    if (action === "screenshot") {
      return "\n\n⚠️ Note: You've screenshotted this page multiple times. Consider asking the user for guidance if you're stuck.";
    }
    return "\n\n⚠️ Note: You've performed this action multiple times. Consider asking the user for help if you're not making progress.";
  }
  return null;
}

function getRecurringErrorWarning(): string | null {
  const recurring: string[] = [];

  for (const [key, error] of consoleErrors) {
    if (error.count >= 3) {
      recurring.push(`Console: "${error.message}" (${error.count}x)`);
    }
  }

  for (const [key, error] of networkErrors) {
    if (error.count >= 3) {
      recurring.push(`Network: ${error.status} ${error.url} (${error.count}x)`);
    }
  }

  if (recurring.length > 0) {
    return `\n\n⚠️ Recurring errors detected - may need human investigation:\n${recurring.join("\n")}`;
  }
  return null;
}

async function ensureBrowser(): Promise<Page> {
  if (!browser || !browser.isConnected()) {
    browser = await chromium.launch({ headless: true });
    context = await browser.newContext();
    page = await context.newPage();

    // Set up console listener
    page.on("console", (msg: ConsoleMessage) => {
      if (msg.type() === "error" || msg.type() === "warning") {
        const text = msg.text();
        const existing = consoleErrors.get(text);
        if (existing) {
          existing.count++;
          existing.lastSeen = Date.now();
        } else {
          consoleErrors.set(text, {
            message: text,
            count: 1,
            firstSeen: Date.now(),
            lastSeen: Date.now(),
          });
        }
      }
    });

    // Set up network error listener
    page.on("response", async (response) => {
      if (response.status() >= 400) {
        const url = response.url();
        const status = response.status();
        const key = `${status}:${url}`;

        const existing = networkErrors.get(key);
        if (existing) {
          existing.count++;
          existing.lastSeen = Date.now();
        } else {
          networkErrors.set(key, {
            message: `${status} ${response.statusText()}`,
            url,
            status,
            count: 1,
            firstSeen: Date.now(),
            lastSeen: Date.now(),
          });
        }
      }
    });
  }

  if (!page) {
    throw new Error("Failed to create page");
  }

  return page;
}

function resolveUrl(url: string): string {
  if (url.startsWith("http://") || url.startsWith("https://")) {
    return url;
  }
  // Relative URL - append to base
  const base = BASE_URL.endsWith("/") ? BASE_URL.slice(0, -1) : BASE_URL;
  const path = url.startsWith("/") ? url : `/${url}`;
  return `${base}${path}`;
}

const server = new Server(
  {
    name: "arxdev-frontend",
    version: "1.0.0",
  },
  {
    capabilities: {
      tools: {},
    },
  }
);

// List available tools
server.setRequestHandler(ListToolsRequestSchema, async () => {
  return {
    tools: [
      {
        name: "navigate",
        description: "Navigate to a URL. Relative URLs use the base URL (default: localhost:5173).",
        inputSchema: {
          type: "object",
          properties: {
            url: {
              type: "string",
              description: "URL to navigate to (relative or absolute)",
            },
          },
          required: ["url"],
        },
      },
      {
        name: "screenshot",
        description: "Take a screenshot of the current page or a specific element. Returns base64 image.",
        inputSchema: {
          type: "object",
          properties: {
            selector: {
              type: "string",
              description: "Optional CSS selector to screenshot specific element",
            },
            fullPage: {
              type: "boolean",
              description: "Capture full scrollable page (default: true)",
            },
          },
        },
      },
      {
        name: "click",
        description: "Click an element by CSS selector or visible text.",
        inputSchema: {
          type: "object",
          properties: {
            selector: {
              type: "string",
              description: "CSS selector of element to click",
            },
            text: {
              type: "string",
              description: "Visible text of element to click (alternative to selector)",
            },
          },
        },
      },
      {
        name: "fill",
        description: "Fill a form input field.",
        inputSchema: {
          type: "object",
          properties: {
            selector: {
              type: "string",
              description: "CSS selector of input field",
            },
            value: {
              type: "string",
              description: "Value to fill",
            },
          },
          required: ["selector", "value"],
        },
      },
      {
        name: "select",
        description: "Select an option from a dropdown.",
        inputSchema: {
          type: "object",
          properties: {
            selector: {
              type: "string",
              description: "CSS selector of select element",
            },
            value: {
              type: "string",
              description: "Value or label to select",
            },
          },
          required: ["selector", "value"],
        },
      },
      {
        name: "get_page_content",
        description: "Get the text content or HTML of the page or a specific element.",
        inputSchema: {
          type: "object",
          properties: {
            selector: {
              type: "string",
              description: "Optional CSS selector to get content of specific element",
            },
            html: {
              type: "boolean",
              description: "Return HTML instead of text (default: false)",
            },
          },
        },
      },
      {
        name: "get_console_logs",
        description: "Get console errors and warnings since last check.",
        inputSchema: {
          type: "object",
          properties: {
            clear: {
              type: "boolean",
              description: "Clear logs after returning (default: true)",
            },
          },
        },
      },
      {
        name: "get_network_errors",
        description: "Get failed network requests (4xx, 5xx) since last check.",
        inputSchema: {
          type: "object",
          properties: {
            clear: {
              type: "boolean",
              description: "Clear errors after returning (default: true)",
            },
          },
        },
      },
      {
        name: "login",
        description: "Log in using test credentials from environment variables (TEST_USERNAME, TEST_PASSWORD).",
        inputSchema: {
          type: "object",
          properties: {},
        },
      },
      {
        name: "accessibility_check",
        description: "Run accessibility audit on the page or a specific element.",
        inputSchema: {
          type: "object",
          properties: {
            selector: {
              type: "string",
              description: "Optional CSS selector to audit specific element",
            },
          },
        },
      },
    ],
  };
});

// Handle tool calls
server.setRequestHandler(CallToolRequestSchema, async (request) => {
  const { name, arguments: args } = request.params;

  try {
    switch (name) {
      case "navigate": {
        const { url } = args as { url: string };
        const fullUrl = resolveUrl(url);
        const page = await ensureBrowser();

        await page.goto(fullUrl, { waitUntil: "networkidle", timeout: 30000 });
        trackAction("navigate", fullUrl);

        const title = await page.title();
        const currentUrl = page.url();

        return {
          content: [
            {
              type: "text",
              text: `Navigated to: ${currentUrl}\nTitle: ${title}`,
            },
          ],
        };
      }

      case "screenshot": {
        const { selector, fullPage = true } = args as { selector?: string; fullPage?: boolean };
        const page = await ensureBrowser();
        const currentUrl = page.url();

        trackAction("screenshot", currentUrl, selector);

        let buffer: Buffer;
        if (selector) {
          const element = await page.$(selector);
          if (!element) {
            return {
              content: [{ type: "text", text: `Element not found: ${selector}` }],
            };
          }
          buffer = await element.screenshot();
        } else {
          buffer = await page.screenshot({ fullPage });
        }

        const base64 = buffer.toString("base64");
        const churnWarning = checkForChurn("screenshot", currentUrl) || "";

        return {
          content: [
            {
              type: "image",
              data: base64,
              mimeType: "image/png",
            },
            {
              type: "text",
              text: `Screenshot of ${currentUrl}${selector ? ` (element: ${selector})` : ""}${churnWarning}`,
            },
          ],
        };
      }

      case "click": {
        const { selector, text } = args as { selector?: string; text?: string };
        const page = await ensureBrowser();

        if (!selector && !text) {
          return {
            content: [{ type: "text", text: "Error: Must provide either selector or text" }],
          };
        }

        trackAction("click", page.url(), selector || text);

        if (text) {
          await page.getByText(text, { exact: false }).click({ timeout: 5000 });
        } else if (selector) {
          await page.click(selector, { timeout: 5000 });
        }

        // Wait briefly for any navigation or updates
        await page.waitForTimeout(500);

        const currentUrl = page.url();
        return {
          content: [
            {
              type: "text",
              text: `Clicked ${text ? `text "${text}"` : `selector "${selector}"`}\nCurrent URL: ${currentUrl}`,
            },
          ],
        };
      }

      case "fill": {
        const { selector, value } = args as { selector: string; value: string };
        const page = await ensureBrowser();

        trackAction("fill", page.url(), selector);

        await page.fill(selector, value, { timeout: 5000 });

        return {
          content: [
            {
              type: "text",
              text: `Filled "${selector}" with value`,
            },
          ],
        };
      }

      case "select": {
        const { selector, value } = args as { selector: string; value: string };
        const page = await ensureBrowser();

        trackAction("select", page.url(), selector);

        await page.selectOption(selector, value, { timeout: 5000 });

        return {
          content: [
            {
              type: "text",
              text: `Selected "${value}" in "${selector}"`,
            },
          ],
        };
      }

      case "get_page_content": {
        const { selector, html = false } = args as { selector?: string; html?: boolean };
        const page = await ensureBrowser();

        let content: string;
        if (selector) {
          const element = await page.$(selector);
          if (!element) {
            return {
              content: [{ type: "text", text: `Element not found: ${selector}` }],
            };
          }
          content = html
            ? await element.innerHTML()
            : await element.textContent() || "";
        } else {
          content = html
            ? await page.content()
            : await page.textContent("body") || "";
        }

        // Truncate if very long
        if (content.length > 10000) {
          content = content.slice(0, 10000) + "\n\n... (truncated)";
        }

        return {
          content: [
            {
              type: "text",
              text: content,
            },
          ],
        };
      }

      case "get_console_logs": {
        const { clear = true } = args as { clear?: boolean };

        if (consoleErrors.size === 0) {
          return {
            content: [{ type: "text", text: "No console errors or warnings." }],
          };
        }

        const logs = Array.from(consoleErrors.values())
          .map((e) => `[${e.count}x] ${e.message}`)
          .join("\n");

        const recurringWarning = getRecurringErrorWarning() || "";

        if (clear) {
          consoleErrors.clear();
        }

        return {
          content: [
            {
              type: "text",
              text: `Console errors/warnings:\n${logs}${recurringWarning}`,
            },
          ],
        };
      }

      case "get_network_errors": {
        const { clear = true } = args as { clear?: boolean };

        if (networkErrors.size === 0) {
          return {
            content: [{ type: "text", text: "No network errors." }],
          };
        }

        const errors = Array.from(networkErrors.values())
          .map((e) => `[${e.count}x] ${e.status} ${e.url}`)
          .join("\n");

        const recurringWarning = getRecurringErrorWarning() || "";

        if (clear) {
          networkErrors.clear();
        }

        return {
          content: [
            {
              type: "text",
              text: `Network errors:\n${errors}${recurringWarning}`,
            },
          ],
        };
      }

      case "login": {
        if (!TEST_USERNAME || !TEST_PASSWORD) {
          return {
            content: [
              {
                type: "text",
                text: "Error: TEST_USERNAME and TEST_PASSWORD environment variables must be set",
              },
            ],
          };
        }

        const page = await ensureBrowser();

        // Navigate to login page
        const loginUrl = resolveUrl("/login");
        await page.goto(loginUrl, { waitUntil: "networkidle", timeout: 30000 });

        // Fill login form - adjust selectors based on actual form
        await page.fill('input[name="username"], input[type="email"], #username, #email', TEST_USERNAME, { timeout: 5000 });
        await page.fill('input[name="password"], input[type="password"], #password', TEST_PASSWORD, { timeout: 5000 });

        // Submit
        await page.click('button[type="submit"], input[type="submit"]', { timeout: 5000 });

        // Wait for navigation
        await page.waitForLoadState("networkidle", { timeout: 30000 });

        const currentUrl = page.url();
        const title = await page.title();

        return {
          content: [
            {
              type: "text",
              text: `Login attempted.\nCurrent URL: ${currentUrl}\nTitle: ${title}`,
            },
          ],
        };
      }

      case "accessibility_check": {
        const { selector } = args as { selector?: string };
        const page = await ensureBrowser();

        // Use Playwright's built-in accessibility snapshot
        // Cast to any since TypeScript types don't expose this experimental API
        const snapshot = await (page as any).accessibility.snapshot({ root: selector ? await page.$(selector) || undefined : undefined });

        if (!snapshot) {
          return {
            content: [{ type: "text", text: "Could not get accessibility tree" }],
          };
        }

        // Format the accessibility tree
        const formatNode = (node: any, indent = 0): string => {
          const prefix = "  ".repeat(indent);
          let result = `${prefix}${node.role}`;
          if (node.name) result += `: "${node.name}"`;
          if (node.value) result += ` [value: ${node.value}]`;
          if (node.checked !== undefined) result += ` [checked: ${node.checked}]`;
          if (node.disabled) result += " [disabled]";
          result += "\n";

          if (node.children) {
            for (const child of node.children) {
              result += formatNode(child, indent + 1);
            }
          }
          return result;
        };

        const tree = formatNode(snapshot);

        return {
          content: [
            {
              type: "text",
              text: `Accessibility tree:\n${tree}`,
            },
          ],
        };
      }

      default:
        throw new Error(`Unknown tool: ${name}`);
    }
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    return {
      content: [
        {
          type: "text",
          text: `Error: ${message}`,
        },
      ],
    };
  }
});

// Cleanup on exit
process.on("SIGINT", async () => {
  if (browser) {
    await browser.close();
  }
  process.exit(0);
});

process.on("SIGTERM", async () => {
  if (browser) {
    await browser.close();
  }
  process.exit(0);
});

// Start the server
async function main() {
  const transport = new StdioServerTransport();
  await server.connect(transport);
  console.error("arxdev-frontend MCP server running on stdio");
  console.error(`Base URL: ${BASE_URL}`);
}

main().catch((error) => {
  console.error("Fatal error:", error);
  process.exit(1);
});
