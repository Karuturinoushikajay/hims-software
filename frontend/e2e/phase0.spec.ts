import { expect, test } from "@playwright/test";

const password = process.env.DEMO_SEED_PASSWORD || "ChangeMeDemo!2026";

test.describe("Phase 0 smoke", () => {
  test("facility admin can login and open users", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel(/username/i).fill("facadmin");
    await page.getByLabel(/password/i).fill(password);
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.getByText(/welcome/i)).toBeVisible({ timeout: 15_000 });
    await page.getByRole("link", { name: /users/i }).click();
    await expect(page.getByRole("heading", { name: /users/i })).toBeVisible();
    await page.getByLabel(/^username$/i).fill(`e2e_${Date.now()}`);
    await page.getByLabel(/^password$/i).fill("TempPass!2026");
    await page.getByLabel(/role/i).selectOption({ label: "Receptionist" });
    await page.getByRole("button", { name: /^create$/i }).click();
    await expect(page.getByText(/e2e_/)).toBeVisible({ timeout: 10_000 });
  });

  test("cashier is denied users admin", async ({ page }) => {
    await page.goto("/");
    await page.getByLabel(/username/i).fill("cashier");
    await page.getByLabel(/password/i).fill(password);
    await page.getByRole("button", { name: /sign in/i }).click();
    await expect(page.getByText(/welcome/i)).toBeVisible({ timeout: 15_000 });
    await page.goto("/users");
    await expect(page.getByRole("alert")).toContainText(/permission|forbidden|missing/i);
  });
});
