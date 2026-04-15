// Run: node test-visual.js
// Screenshots saved to /tmp/ss-*.png — open them in Finder to review
//
// Prerequisites:
//   npm install playwright (already installed)
//   Frontend running: cd frontend && npm run dev
//   Backend running: docker compose up -d

const { chromium } = require("playwright");

async function run() {
  const browser = await chromium.launch();

  // --- DESKTOP (1280x900) ---
  const desktop = await browser.newPage({ viewport: { width: 1280, height: 900 } });

  // 1. Events browse
  await desktop.goto("http://localhost:5173/events");
  await desktop.waitForTimeout(3000);
  await desktop.screenshot({ path: "/tmp/ss-desktop-events.png", fullPage: true });
  console.log("✓ desktop events browse");

  // 2. Click into event detail
  await desktop.click("text=E2E Seed Event");
  await desktop.waitForTimeout(2000);
  await desktop.screenshot({ path: "/tmp/ss-desktop-detail.png", fullPage: true });
  console.log("✓ desktop event detail");

  // 3. Click Sign Up to show the form
  const btns = await desktop.locator('button:has-text("Sign Up")').all();
  if (btns.length > 0) await btns[0].click();
  await desktop.waitForTimeout(500);
  await desktop.screenshot({ path: "/tmp/ss-desktop-form.png", fullPage: true });
  console.log("✓ desktop signup form");

  // 4. Login page
  await desktop.goto("http://localhost:5173/login");
  await desktop.waitForTimeout(2000);
  await desktop.screenshot({ path: "/tmp/ss-desktop-login.png", fullPage: true });
  console.log("✓ desktop login");

  // 5. Log in as admin
  await desktop.fill('input[type="email"]', "admin@e2e.example.com");
  await desktop.fill('input[type="password"]', "Admin!2345");
  await desktop.click('button[type="submit"]');
  await desktop.waitForTimeout(3000);
  await desktop.screenshot({ path: "/tmp/ss-desktop-admin-home.png", fullPage: true });
  console.log("✓ desktop admin home (after login)");

  // 6. Organizer page
  await desktop.goto("http://localhost:5173/organizer");
  await desktop.waitForTimeout(2000);
  await desktop.screenshot({ path: "/tmp/ss-desktop-organizer.png", fullPage: true });
  console.log("✓ desktop organizer");

  // 7. Audit logs
  await desktop.goto("http://localhost:5173/admin/audit-logs");
  await desktop.waitForTimeout(2000);
  await desktop.screenshot({ path: "/tmp/ss-desktop-audit.png", fullPage: true });
  console.log("✓ desktop audit logs");

  await desktop.close();

  // --- MOBILE (375x812, iPhone-sized) ---
  const mobile = await browser.newPage({ viewport: { width: 375, height: 812 } });

  await mobile.goto("http://localhost:5173/events");
  await mobile.waitForTimeout(3000);
  await mobile.screenshot({ path: "/tmp/ss-mobile-events.png", fullPage: true });
  console.log("✓ mobile events browse");

  await mobile.click("text=E2E Seed Event");
  await mobile.waitForTimeout(2000);
  await mobile.screenshot({ path: "/tmp/ss-mobile-detail.png", fullPage: true });
  console.log("✓ mobile event detail");

  await mobile.close();
  await browser.close();

  console.log("\nAll done! Open screenshots:");
  console.log("  open /tmp/ss-desktop-*.png");
  console.log("  open /tmp/ss-mobile-*.png");
}

run().catch(console.error);
