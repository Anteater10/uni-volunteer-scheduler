// Phase 1: axe-core a11y scan — hard merge gate. Any WCAG 2.1 AA violation fails the PR.
import { test, expect } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { STUDENT, ORGANIZER, ADMIN, getSeed, ephemeralEmail } from "./fixtures.js";

const AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"];
const AXE_OPTIONS = { rules: { "target-size": { enabled: true } } };

function assertNoViolations(results) {
  const summary = results.violations.map((v) => ({
    id: v.id,
    desc: v.description,
    nodes: v.nodes.length,
  }));
  expect(results.violations, JSON.stringify(summary, null, 2)).toEqual([]);
}

async function scanPage(page) {
  const results = await new AxeBuilder({ page })
    .withTags(AXE_TAGS)
    .options(AXE_OPTIONS)
    .analyze();
  assertNoViolations(results);
}

async function loginAs(page, creds) {
  await page.goto("/login");
  await page.getByLabel(/^email/i).fill(creds.email);
  await page.getByLabel(/password/i).fill(creds.password);
  await page.getByRole("button", { name: /log\s?in|sign\s?in/i }).click();
  await page.waitForURL(/\/(events|admin|organizer|my-signups)/);
}

// ── Public routes (no auth) ──

test.describe("a11y: public routes", () => {
  test("/ (root)", async ({ page }) => {
    await page.goto("/");
    await page.waitForLoadState("networkidle");
    await scanPage(page);
  });

  test("/events", async ({ page }) => {
    await page.goto("/events");
    await page.waitForLoadState("networkidle");
    await scanPage(page);
  });

  test("/login", async ({ page }) => {
    await page.goto("/login");
    await page.waitForLoadState("networkidle");
    await scanPage(page);
  });

  test("/register", async ({ page }) => {
    await page.goto("/register");
    await page.waitForLoadState("networkidle");
    await scanPage(page);
  });
});

// ── Student routes ──

test.describe("a11y: student routes", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, STUDENT);
  });

  test("/events (authed)", async ({ page }) => {
    await page.goto("/events");
    await page.waitForLoadState("networkidle");
    await scanPage(page);
  });

  test("/my-signups", async ({ page }) => {
    await page.goto("/my-signups");
    await page.waitForLoadState("networkidle");
    await scanPage(page);
  });

  test("/profile", async ({ page }) => {
    await page.goto("/profile");
    await page.waitForLoadState("networkidle");
    await scanPage(page);
  });

  test("signup modal on /events/:id", async ({ page }) => {
    const seed = getSeed();
    if (!seed.event_id) {
      test.skip(true, "no seeded event_id");
      return;
    }
    await page.goto(`/events/${seed.event_id}`);
    await page.waitForLoadState("networkidle");

    // Open signup modal by clicking first "Sign up" button
    const btn = page.getByTestId("slot-signup-button").first();
    if ((await btn.count()) > 0) {
      await btn.click();
      await expect(page.getByRole("dialog")).toBeVisible();
      // Scan with modal open
      await scanPage(page);
    } else {
      // No signup button visible — scan page as-is
      await scanPage(page);
    }
  });
});

// ── Organizer routes ──

test.describe("a11y: organizer routes", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, ORGANIZER);
  });

  test("/organizer", async ({ page }) => {
    await page.goto("/organizer");
    await page.waitForLoadState("networkidle");
    await scanPage(page);
  });

  test("/organizer/events/:id", async ({ page }) => {
    const seed = getSeed();
    if (!seed.event_id) {
      test.skip(true, "no seeded event_id");
      return;
    }
    await page.goto(`/organizer/events/${seed.event_id}`);
    await page.waitForLoadState("networkidle");
    await scanPage(page);
  });
});

// ── Admin routes ──

test.describe("a11y: admin routes", () => {
  test.beforeEach(async ({ page }) => {
    await loginAs(page, ADMIN);
  });

  test("/admin", async ({ page }) => {
    await page.goto("/admin");
    await page.waitForLoadState("networkidle");
    await scanPage(page);
  });

  test("/admin/users", async ({ page }) => {
    await page.goto("/admin/users");
    await page.waitForLoadState("networkidle");
    await scanPage(page);
  });

  test("/admin/portals", async ({ page }) => {
    await page.goto("/admin/portals");
    await page.waitForLoadState("networkidle");
    await scanPage(page);
  });
});
