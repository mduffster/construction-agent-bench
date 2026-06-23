import { expect, test } from "@playwright/test";

const roles = ["steel supplier", "general contractor", "owner", "labor subcontractor"];

test("homepage, actor selection, and results page render", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /goals/i })).toBeVisible();
  await page.getByRole("link", { name: /compare outcomes/i }).click();
  await expect(page.getByRole("heading", { name: /outcome comparison/i })).toBeVisible();
  await expect(page.getByText(/ideal: everyone coordinates/i)).toBeVisible();
  await expect(page.getByText("Claude Haiku all-agent run", { exact: true })).toBeVisible();
  await page.getByRole("link", { name: /play/i }).click();
  await expect(page.getByText(/choose your organization/i)).toBeVisible();
  await expect(page.getByText(/system participants/i)).toBeVisible();
});

for (const role of roles) {
  test(`${role} can complete a three-round S01 playthrough`, async ({ page }) => {
    await page.goto("/play");
    await page.getByRole("link", { name: new RegExp(role, "i") }).click();
    await expect(page.getByText(/scenario briefing/i)).toBeVisible();
    await expect(page.getByText(/project snapshot/i)).toBeVisible();
    await page.getByRole("button", { name: /start first decision/i }).click();

    for (let round = 0; round < 3; round += 1) {
      await expect(page.getByRole("heading", { name: /public info/i })).toBeVisible();
      await expect(page.getByRole("heading", { name: /private info/i })).toBeVisible();
      await page.locator("button.choice-card").first().click();
      await expect(page.getByRole("heading", { name: /what happened/i })).toBeVisible();
      await expect(page.getByText(/project impacts this round/i)).toBeVisible();
      await page.getByRole("button", { name: /update partner trust/i }).click();
      await expect(page.getByRole("heading", { name: /has your counterparty trust changed/i })).toBeVisible();
      await page.getByRole("button", { name: /continue|show final outcome/i }).click();
    }

    await expect(page.getByText(/final outcome/i)).toBeVisible();
    await expect(page.getByText(/trust summary/i)).toBeVisible();
    await expect(page.getByText(/average partner trust/i)).toBeVisible();
    await expect(page.getByText(/your playthrough/i)).toBeVisible();
  });
}
