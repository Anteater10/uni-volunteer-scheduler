// e2e/copilot-citations.spec.js
//
// Phase 32 Plan 06 — citation-chip click-through smoke.
//
// Strategy: mock the Phase 30 SSE endpoint + the Plan 32-05 citation detail
// endpoint at the network layer (page.route). This keeps the spec
// hermetic — no embedding model, no Postgres pgvector, no retrieval — and
// runs reliably across all 6 Playwright projects (chromium, firefox, webkit,
// Mobile Chrome, Mobile Safari, iPhone SE 375).
//
// Auto-picked-up by the CI matrix: .github/workflows/ci.yml runs
// `npx playwright test` with no spec list, so playwright.config.js's default
// testMatch globs this file and runs it under every project. See
// 32-06-SUMMARY.md "Task 3b" for the grep proof.

import { test, expect } from '@playwright/test';
import { ADMIN } from './fixtures.js';

const CITATIONS_TURN_1 = [
  {
    chunk_id: '11111111-1111-1111-1111-111111111111',
    source_path: 'docs/learning/30-streaming-chat-mvp/01-sse.md',
    char_start: 0,
    char_end: 42,
    quote: 'Server-sent events deliver tokens incrementally.',
    rrf_score: 0.91,
    rerank_score: 0.88,
  },
  {
    chunk_id: '22222222-2222-2222-2222-222222222222',
    source_path: 'docs/learning/32-rag-retrieval/02-hybrid.md',
    char_start: 100,
    char_end: 200,
    quote: 'RRF fuses dense and lexical rankings without tuning.',
    rrf_score: 0.85,
    rerank_score: 0.83,
  },
];

const CITATIONS_TURN_2 = [
  {
    chunk_id: '33333333-3333-3333-3333-333333333333',
    source_path: 'docs/learning/32-rag-retrieval/03-rerank.md',
    char_start: 0,
    char_end: 10,
    quote: 'Cross-encoder rerank improves precision at small k.',
    rrf_score: 0.9,
    rerank_score: 0.95,
  },
];

function sseBody(events) {
  return events.map((e) => `event: ${e.event}\ndata: ${e.data}\n\n`).join('');
}

async function loginAs(page, who) {
  await page.goto('/login');
  await page.locator('#login-email').fill(who.email);
  await page.locator('#login-password').fill(who.password);
  await page.getByRole('button', { name: /log.?in|sign.?in/i }).click();
  await expect(page).not.toHaveURL(/\/login$/, { timeout: 8000 });
}

// Mock the copilot endpoints. The FAB lazily creates a session on first open,
// then POSTs to /sessions/{id}/messages for each user turn.
async function installCopilotMocks(page) {
  let turnCount = 0;

  await page.route(/\/api\/v1\/copilot\/sessions(\/[^/]+)?$/, async (route) => {
    const url = route.request().url();
    if (route.request().method() === 'POST' && /\/sessions$/.test(url)) {
      // createSession
      return route.fulfill({
        status: 201,
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ id: 'mock-session-1' }),
      });
    }
    return route.fallback();
  });

  await page.route(/\/api\/v1\/copilot\/sessions\/[^/]+\/messages$/, async (route) => {
    if (route.request().method() !== 'POST') return route.fallback();
    turnCount += 1;
    const citations = turnCount === 1 ? CITATIONS_TURN_1 : CITATIONS_TURN_2;
    const body = sseBody([
      {
        event: 'meta',
        data: JSON.stringify({
          citations,
          retrieval_latency_ms: 12,
          rerank_latency_ms: 34,
        }),
      },
      { event: 'token', data: '"Mock"' },
      { event: 'token', data: '" answer"' },
      { event: 'done', data: '{"message_id":"asst-mock"}' },
    ]);
    return route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'text/event-stream' },
      body,
    });
  });

  await page.route(/\/api\/v1\/copilot\/citations\/([0-9a-f-]+)$/, async (route) => {
    const url = route.request().url();
    const id = url.split('/').pop();
    return route.fulfill({
      status: 200,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        source_path: 'docs/learning/30-streaming-chat-mvp/01-sse.md',
        char_start: 0,
        char_end: 42,
        content: `Mock full source content for chunk ${id}.`,
        document_url: '',
      }),
    });
  });
}

test.describe('copilot citation chips — click-through smoke', () => {
  test.beforeEach(async ({ page }) => {
    await page.setViewportSize({ width: 1280, height: 800 });
    await installCopilotMocks(page);
    await loginAs(page, ADMIN);
  });

  test('renders chips from meta event, click opens panel, second turn replaces chips', async ({ page }) => {
    // Open the copilot drawer via the FAB
    await page.getByRole('button', { name: /open scitrek copilot/i }).click();
    await expect(page.getByRole('dialog', { name: /scitrek copilot/i })).toBeVisible();

    // Send first message
    const input = page.getByRole('textbox', { name: 'Message' });
    await expect(input).toBeEnabled();
    await input.fill('What is SSE?');
    await page.getByRole('button', { name: /send message/i }).click();

    // Assistant content + chips appear
    await expect(page.getByText('Mock answer')).toBeVisible();
    const list = page.getByRole('list', { name: /sources consulted/i });
    await expect(list).toBeVisible();
    await expect(page.getByRole('button', { name: /citation 1/i })).toBeVisible();
    await expect(page.getByRole('button', { name: /citation 2/i })).toBeVisible();

    // Click chip 1 -> panel opens with mocked source content
    await page.getByRole('button', { name: /citation 1/i }).click();
    await expect(page.getByRole('dialog', { name: /source consulted/i })).toBeVisible();
    await expect(page.getByText(/mock full source content/i)).toBeVisible();

    // External link is hidden (document_url is "")
    await expect(page.getByRole('link', { name: /open source/i })).toHaveCount(0);

    // Close the panel
    await page.getByRole('button', { name: /close source panel/i }).click();
    await expect(page.getByRole('dialog', { name: /source consulted/i })).not.toBeVisible();

    // Send a second message — its citation set should be independent of turn 1.
    // Per-message snapshotting means turn 1's chips remain anchored under turn
    // 1's bubble; turn 2 gets its own (smaller, 1-chip) row.
    await input.fill('What is rerank?');
    await page.getByRole('button', { name: /send message/i }).click();
    await expect(page.getByText('Mock answer')).toHaveCount(2); // 2 assistant messages now
    // Two chip rows total (one per assistant message).
    await expect(page.getByRole('list', { name: /sources consulted/i })).toHaveCount(2);
    // Turn 1 had 2 chips, turn 2 has 1 chip — so [1] appears twice, [2] once.
    await expect(page.getByRole('button', { name: /citation 1/i })).toHaveCount(2);
    await expect(page.getByRole('button', { name: /citation 2/i })).toHaveCount(1);
  });
});
