// Phase 1: Asserts the signup flow completes in <= 3 taps with no URL change.
// 3-tap budget: tap 1 = slot "Sign up" button, tap 2 = "Confirm signup" in modal.
import { test, expect } from "@playwright/test";
import { STUDENT, getSeed, ephemeralEmail } from "./fixtures.js";

async function loginAs(page, creds) {
  await page.goto("/login");
  await page.getByLabel(/^email/i).fill(creds.email);
  await page.getByLabel(/password/i).fill(creds.password);
  await page.getByRole("button", { name: /log\s?in|sign\s?in/i }).click();
  await page.waitForURL(/\/(events|my-signups)/);
}

test("signup completes in <= 3 taps with no URL change", async ({ page }) => {
  const seed = getSeed();
  expect(seed.event_id, "seed did not populate event_id").toBeTruthy();

  // Use an ephemeral student so the slot is not already signed-up
  const email = ephemeralEmail("threetap");
  const password = "Student!2345";

  // Register a fresh student
  await page.goto("/register");
  await page.getByLabel(/full name/i).fill("Three Tap");
  await page.getByLabel(/^email/i).fill(email);
  await page.getByLabel(/password/i).fill(password);
  await page.getByRole("button", { name: /create account|register|sign\s?up/i }).click();
  await page.waitForURL(/\/(events|my-signups)/);

  // Navigate to seeded event
  await page.goto(`/events/${seed.event_id}`);
  await page.waitForLoadState("networkidle");

  const startUrl = page.url();

  // Tap 1: click first "Sign up" button on a slot
  const signupBtn = page.getByTestId("slot-signup-button").first();
  await expect(signupBtn).toBeVisible();
  await signupBtn.click();

  // Assert modal is visible
  await expect(page.getByRole("dialog")).toBeVisible();
  // Assert URL unchanged
  expect(page.url()).toBe(startUrl);

  // Tap 2: click "Confirm signup" in the modal
  const confirmBtn = page.getByTestId("confirm-signup-button");
  await expect(confirmBtn).toBeVisible();
  await confirmBtn.click();

  // Assert modal closed
  await expect(page.getByRole("dialog")).not.toBeVisible();
  // Assert toast visible
  await expect(page.getByRole("status")).toBeVisible();
  // Assert URL still unchanged — no navigations between taps
  expect(page.url()).toBe(startUrl);
});
