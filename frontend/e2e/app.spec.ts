import { test, expect } from "@playwright/test";

test("homepage loads and shows chat interface", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle(/InsightXpert/i);
});

test("can type a message in the chat input", async ({ page }) => {
  await page.goto("/");

  const input = page.getByPlaceholder(/ask/i);
  await expect(input).toBeVisible();
  await input.fill("Show me total transactions");
  await expect(input).toHaveValue("Show me total transactions");
});
