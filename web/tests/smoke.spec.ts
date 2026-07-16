import { expect, test } from "@playwright/test";

const roles = ["steel supplier", "general contractor", "owner", "labor subcontractor"];

test("homepage, actor selection, and results page render", async ({ page }) => {
  await page.goto("/");
  await expect(page).toHaveTitle("ConstructSim");
  await expect(page.getByRole("heading", { name: "ConstructSim" })).toBeVisible();
  await expect(page.getByRole("link", { name: "Twitter", exact: true })).toHaveAttribute(
    "href",
    "https://x.com/iammattduff"
  );
  await expect(page.getByRole("link", { name: "Substack", exact: true })).toHaveAttribute(
    "href",
    "https://seekingsignal.substack.com"
  );
  await expect(page.getByRole("heading", { name: /what we're testing/i })).toBeVisible();
  await expect(page.getByRole("link", { name: /^try it$/i })).toHaveAttribute("href", "/play");
  await page.getByRole("link", { name: /see example runs/i }).click();
  await expect(page.getByRole("heading", { name: /how to read these numbers/i })).toBeVisible();
  await expect(page.getByText(/success limits/i)).toBeVisible();
  await expect(page.getByRole("heading", { name: /project succeeds but firms still lose/i })).toBeVisible();
  await expect(page.getByText(/firms met target/i).first()).toBeVisible();
  await expect(page.getByText(/failed — too late/i).first()).toBeVisible();
  await expect(page.getByText(/success — some firms lost/i).first()).toBeVisible();
  await expect(page.getByText(/^repairs$/i)).toBeVisible();
  await expect(page.getByRole("heading", { name: /scripted reference paths/i })).toBeVisible();
  await expect(page.getByText(/coordinated phased success/i)).toBeVisible();
  await expect(page.getByText(/excessive-caution failure/i)).toBeVisible();
  await expect(page.getByText(/panic-spending failure/i)).toBeVisible();
  await page.getByRole("link", { name: /play/i }).click();
  await expect(page.getByText(/choose your organization/i)).toBeVisible();
  await expect(page.getByText(/system participants/i)).toBeVisible();
});

test("research page publishes the staged research evidence", async ({ page }) => {
  await page.goto("/research");
  await expect(
    page.getByRole("heading", { name: /from one decision to six firms/i })
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: /can one supplier adjust its price/i })).toBeVisible();
  await expect(page.getByText(/46\/50 runs/i)).toBeVisible();
  await expect(page.getByText(/15-run Sonnet confirmation/i)).toBeVisible();
  await expect(page.getByText("Average avoidable loss", { exact: true }).first()).toBeVisible();
  await expect(page.getByRole("img", { name: /response curve comparing/i })).toBeVisible();
  await expect(page.getByRole("table", { name: /response curve values/i })).toBeVisible();
  await expect(page.getByText(/results come from one simulated construction problem/i)).toBeVisible();
  await expect(page.getByRole("heading", { name: /what explains the supplier failure/i })).toBeVisible();
  await expect(page.getByText(/highest safe request provided/i)).toBeVisible();
  await expect(page.getByText(/88% less avoidable loss/i)).toBeVisible();
  await expect(page.getByRole("heading", { name: /pass a useful number to another/i })).toBeVisible();
  await expect(page.getByRole("table", { name: /two-agent handoff results/i })).toBeVisible();
  await expect(page.getByText(/18\/18/i).first()).toBeVisible();
  await expect(page.getByRole("heading", { name: /more companies use AI/i })).toBeVisible();
  await expect(page.getByRole("table", { name: /controlled multiplayer ladder results/i })).toBeVisible();
  await expect(page.getByText(/information arrived, but the strategy was still expensive/i)).toBeVisible();
  await expect(page.getByRole("heading", { name: /which company needs the decision summary/i })).toBeVisible();
  await expect(page.getByRole("table", { name: /decision summary results/i })).toBeVisible();
  await expect(page.getByText(/supplier summary was sufficient/i)).toBeVisible();
  await expect(page.getByText(/40\/40/i)).toBeVisible();
  await expect(page.getByText(/accounting bug/i)).toHaveCount(0);
  await expect(page.getByText(/private cash limits never appeared in the contractor/i)).toBeVisible();
});

test("end screen shows the crowd comparison when playthrough stats exist", async ({ page }) => {
  let recorded: unknown = null;
  await page.route("**/api/playthroughs*", async (route) => {
    const request = route.request();
    if (request.method() === "POST") {
      recorded = request.postDataJSON();
      await route.fulfill({ status: 201, json: { recorded: true } });
      return;
    }
    await route.fulfill({
      status: 200,
      json: {
        available: true,
        totalPlays: 41,
        rolePlays: 12,
        projectSuccessCount: 9,
        privateSuccessCount: 6,
        averageCostUsd: 96_100_000,
        averageCompletionWeek: 42,
        nodes: {
          S01_A1_SUPPLIER_APPLICATION: { balanced: 7, self_protective: 3, conservative: 2 },
        },
      },
    });
  });

  await page.goto("/play");
  await page.getByRole("link", { name: /steel supplier/i }).click();
  await page.getByRole("button", { name: /start first decision/i }).click();
  for (let round = 0; round < 3; round += 1) {
    await page.locator("button.choice-card").first().click();
    await page.getByRole("button", { name: /continue to next decision|show final outcome/i }).click();
  }

  await expect(page.getByRole("heading", { name: /you vs\. other players/i })).toBeVisible();
  await expect(page.getByText(/12 people have finished a playthrough/i)).toBeVisible();
  await expect(page.getByText(/average player finish/i)).toBeVisible();
  expect(recorded).toMatchObject({ role: "steel_supplier" });
});

test("end screen stays clean when playthrough stats are unavailable", async ({ page }) => {
  await page.route("**/api/playthroughs*", async (route) => {
    if (route.request().method() === "POST") {
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    await route.fulfill({ status: 200, json: { available: false } });
  });

  await page.goto("/play");
  await page.getByRole("link", { name: /owner/i }).click();
  await page.getByRole("button", { name: /start first decision/i }).click();
  for (let round = 0; round < 3; round += 1) {
    await page.locator("button.choice-card").first().click();
    await page.getByRole("button", { name: /continue to next decision|show final outcome/i }).click();
  }

  await expect(page.getByText(/final outcome/i)).toBeVisible();
  await expect(page.getByRole("heading", { name: /you vs\. other players/i })).toHaveCount(0);
});

test.describe("mobile layout", () => {
  test.use({ viewport: { width: 375, height: 812 } });

  test("research program tables fit the phone viewport", async ({ page }) => {
    await page.goto("/research");
    await expect(page.getByRole("heading", { name: /from one decision to six firms/i })).toBeVisible();
    await expect(page.getByRole("table", { name: /two-agent handoff results/i })).toBeVisible();
    await expect(page.getByRole("table", { name: /controlled multiplayer ladder results/i })).toBeVisible();
    await expect(page.getByRole("table", { name: /decision summary results/i })).toBeVisible();
    const dimensions = await page.evaluate(() => ({
      clientWidth: document.documentElement.clientWidth,
      scrollWidth: document.documentElement.scrollWidth,
    }));
    expect(dimensions.scrollWidth).toBeLessThanOrEqual(dimensions.clientWidth);
  });

  test("choice cards stack full-width on phones", async ({ page }) => {
    await page.goto("/play/s01?role=gc");
    await page.getByRole("button", { name: /start first decision/i }).click();
    const firstCard = page.locator("button.choice-card").first();
    await expect(firstCard).toBeVisible();
    const box = await firstCard.boundingBox();
    expect(box).not.toBeNull();
    // Regression guard: cards once rendered as three ~108px columns because a
    // higher-specificity game-shell rule overrode the media-query collapse.
    expect(box!.width).toBeGreaterThan(300);
  });
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
      await expect(page.getByText(/your upside|cost risk|delay risk/i)).toHaveCount(0);
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
      await expect(page.getByText(/trust is optional and does not change the project/i)).toBeVisible();
      await expect(page.getByText(/not graded against the partner/i)).toBeVisible();
      await expect(page.getByText("Charitable read", { exact: true }).first()).toBeVisible();
      await expect(page.getByText("Uncharitable read", { exact: true }).first()).toBeVisible();
      await expect(page.getByRole("slider", { name: /trust rating/i }).first()).toBeVisible();
      await page.getByRole("button", { name: /continue to next decision|show final outcome/i }).click();
    }

    await expect(page.getByText(/final outcome/i)).toBeVisible();
    await expect(page.getByText(/organization target/i)).toBeVisible();
    await expect(page.getByText(/outcome mix/i)).toBeVisible();
    await expect(page.getByText(/^coalition$/i)).toHaveCount(0);
    await expect(page.getByRole("heading", { name: /how did you read your partners/i })).toBeVisible();
    await expect(page.getByText(/partners you chose to rate/i)).toBeVisible();
    await expect(page.getByText(/no trust ratings recorded/i)).toBeVisible();
    await expect(page.locator(".trust-calibration-card").first()).toBeVisible();
    await expect(page.getByText(/your playthrough/i)).toBeVisible();
    await expect(page.getByText(/state-reactive decisions/i)).toBeVisible();
    await expect(page.getByText(/branching script/i)).toHaveCount(0);
  });
}
