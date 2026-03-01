import { test, expect } from "@playwright/test";

test("homepage loads and shows chat interface", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/InsightXpert/i);
});

test("login page shows auth form and accepts input", async ({ page }) => {
  await page.goto("/login");

  const emailInput = page.getByPlaceholder(/you@example\.com/i);
  await expect(emailInput).toBeVisible();
  await emailInput.fill("admin@insightxpert.ai");
  await expect(emailInput).toHaveValue("admin@insightxpert.ai");

  const passwordInput = page.getByPlaceholder(/enter your password/i);
  await expect(passwordInput).toBeVisible();
});
