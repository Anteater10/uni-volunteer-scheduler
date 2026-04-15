/**
 * a11y.spec.js
 *
 * axe-core WCAG 2.1 AA sweep across every public route.
 * Runs under every Playwright project; 375px horizontal-scroll assertion
 * is scoped to iPhone SE 375 project only.
 *
 * Requirements: PART-10 (zero axe violations), PART-11 (375px no h-scroll).
 */

import { test, expect } from '@playwright/test'
import AxeBuilder from '@axe-core/playwright'
import { getSeed } from './fixtures.js'

const WCAG_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa']

// Routes that do not need seeded data — always reachable
const STATIC_ROUTES = [
  { path: '/events', name: 'events browse' },
  { path: '/signup/manage', name: 'manage (no token — error state)' },
]

// Routes parameterized off the E2E seed (require global-setup)
function dynamicRoutes() {
  const seed = getSeed()
  return [
    { path: `/events/${seed.event_id}`, name: 'event detail', needs: 'event_id' },
    {
      path: `/signup/confirm?token=${seed.a11y_confirm_token || seed.confirm_token}`,
      name: 'confirm page',
      needs: 'confirm_token',
    },
    {
      path: `/portals/${seed.portal_slug || 'scitrek'}`,
      name: 'portal landing',
      needs: 'portal_slug',
    },
    {
      path: `/check-in/${seed.signup_id}`,
      name: 'self check-in',
      needs: 'signup_id',
    },
  ]
}

test.describe('a11y — axe-core WCAG 2.1 AA sweep', () => {
  for (const r of STATIC_ROUTES) {
    test(`no violations on ${r.name}`, async ({ page }) => {
      await page.goto(r.path)
      await page.waitForLoadState('networkidle')
      const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze()
      expect(
        results.violations,
        `violations on ${r.path}:\n${JSON.stringify(results.violations, null, 2)}`,
      ).toEqual([])
    })
  }

  for (const r of dynamicRoutes()) {
    test(`no violations on ${r.name}`, async ({ page }) => {
      const seed = getSeed()
      expect(
        seed[r.needs],
        `E2E seed must expose ${r.needs} — run seed_e2e.py`,
      ).toBeTruthy()
      await page.goto(r.path)
      await page.waitForLoadState('networkidle')
      const results = await new AxeBuilder({ page }).withTags(WCAG_TAGS).analyze()
      expect(
        results.violations,
        `violations on ${r.path}:\n${JSON.stringify(results.violations, null, 2)}`,
      ).toEqual([])
    })
  }
})

test.describe('375px viewport — no horizontal scroll', () => {
  // Only run in iPhone SE 375 project (375x667)
  test.beforeEach(async ({}, testInfo) => {
    test.skip(
      testInfo.project.name !== 'iPhone SE 375',
      'h-scroll assertion is scoped to iPhone SE 375 project',
    )
  })

  const ALL_ROUTES = [...STATIC_ROUTES, ...dynamicRoutes()]

  for (const r of ALL_ROUTES) {
    test(`no horizontal scroll on ${r.name} @ 375px`, async ({ page }) => {
      if (r.needs) {
        const seed = getSeed()
        expect(seed[r.needs], `E2E seed must expose ${r.needs}`).toBeTruthy()
      }
      await page.goto(r.path)
      await page.waitForLoadState('networkidle')
      const overflow = await page.evaluate(
        () => document.body.scrollWidth - window.innerWidth,
      )
      expect(
        overflow,
        `${r.path} has ${overflow}px horizontal overflow at 375px`,
      ).toBeLessThanOrEqual(0)
    })
  }
})
