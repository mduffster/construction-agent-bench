import { expect, test } from "@playwright/test";

const roles = ["steel supplier", "general contractor", "owner", "labor subcontractor"];

test("homepage, actor selection, and results page render", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle("ConstructSim");
  await expect(page.getByRole("heading", { name: "ConstructSim" })).toBeVisible();
  await expect(page.getByRole("heading", { name: /goals/i })).toBeVisible();
  await page.getByRole("link", { name: /see example runs/i }).click();
  await expect(page.getByRole("heading", { name: /how to read these numbers/i })).toBeVisible();
  await expect(page.getByText(/success limits/i)).toBeVisible();
  await expect(page.getByRole("heading", { name: /what the ai agents actually did/i })).toBeVisible();
  await expect(page.getByText(/firms met target/i).first()).toBeVisible();
  await expect(page.getByText(/failed — too late/i)).toBeVisible();
  await expect(page.getByRole("heading", { name: /scripted reference paths/i })).toBeVisible();
  await expect(page.getByText(/coordinated phased success/i)).toBeVisible();
  await expect(page.getByText(/excessive-caution failure/i)).toBeVisible();
  await expect(page.getByText(/panic-spending failure/i)).toBeVisible();
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
      await expect(page.getByText(/site view before your decision/i)).toBeVisible();
      await expect(page.locator(".project-postcard__image")).toBeVisible();
      await expect(page.getByRole("heading", { name: /public info/i })).toBeVisible();
      await expect(page.getByRole("heading", { name: /private info/i })).toBeVisible();
      await page.locator("button.choice-card").first().click();
      await expect(page.getByText(/site view after the round/i)).toBeVisible();
      await expect(page.locator(".project-postcard__image")).toBeVisible();
      await expect(page.getByRole("heading", { name: /what happened/i })).toBeVisible();
      if (role === "steel supplier" && round === 0) {
        await expect(
          page.getByRole("heading", { name: /what you told the team vs\. what you know/i })
        ).toBeVisible();
      }
      await expect(page.getByRole("heading", { name: /partner decisions and trust/i })).toBeVisible();
      await expect(page.getByText(/best public and private information/i)).toBeVisible();
      await expect(page.getByText("Charitable read", { exact: true }).first()).toBeVisible();
      await expect(page.getByText("Uncharitable read", { exact: true }).first()).toBeVisible();
      await expect(page.getByRole("slider", { name: /trust rating/i }).first()).toBeVisible();
      await page.getByRole("button", { name: /continue to next decision|show final outcome/i }).click();
    }

    await expect(page.getByText(/final outcome/i)).toBeVisible();
    await expect(page.getByText(/organization target/i)).toBeVisible();
    await expect(page.getByText(/outcome mix/i)).toBeVisible();
    await expect(page.getByText(/^coalition$/i)).toHaveCount(0);
    await expect(page.getByRole("heading", { name: /how well did you read your partners/i })).toBeVisible();
    await expect(page.getByText(/ratings that matched the partner/i)).toBeVisible();
    await expect(page.locator(".trust-calibration-card").first()).toBeVisible();
    await expect(page.getByText(/your playthrough/i)).toBeVisible();
    await expect(page.getByText(/state-reactive decisions/i)).toBeVisible();
    await expect(page.getByText(/branching script/i)).toHaveCount(0);
  });
}
