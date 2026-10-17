import { expect, test } from "@playwright/test";

test("console connects, a rule escalates in mock mode, the operator resolves it, the inspector opens", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("INTERLOCK")).toBeVisible();
  await expect(page.getByText("jev mock")).toBeVisible();
  await expect(page.getByText("No rules yet", { exact: false })).toBeVisible();

  await page.getByRole("button", { name: "+ Speed limit 25 m/s" }).click();
  await expect(page.getByText("checker speed_limit")).toBeVisible();

  await page.getByRole("button", { name: "step", exact: true }).click();
  // Mock mode has no judge: every question is "unavailable" at p = 0.5, so the step escalates,
  // and because nothing is confidently safe the card says no compliant action.
  await expect(page.getByText("waiting on operator")).toBeVisible();
  await expect(page.getByText("judge unavailable", { exact: false })).toBeVisible();
  await expect(page.getByText("No candidate is confidently safe", { exact: false })).toBeVisible();
  await page.getByRole("button", { name: /^deny/ }).click();

  const tick = page.getByRole("button", { name: "inspect step 0" });
  await expect(tick).toBeVisible();
  await tick.click();
  await expect(page.getByText("Inspector · step 0")).toBeVisible();
  await expect(page.getByText("operator deny", { exact: false })).toBeVisible();
  await expect(page.getByText("no compliant action", { exact: false })).toBeVisible();
  await page.keyboard.press("Escape");

  // Second step: the operator overrides with a candidate that is not the proposal.
  await page.getByRole("button", { name: "step", exact: true }).click();
  await expect(page.getByText("waiting on operator")).toBeVisible();
  const override = page.getByRole("button", { name: /: override$/ }).first();
  const chosen = ((await override.getAttribute("aria-label")) ?? "").split(":")[0];
  expect(chosen).toMatch(/^(LANE_LEFT|IDLE|LANE_RIGHT|FASTER|SLOWER)$/);
  await override.click();

  const tick1 = page.getByRole("button", { name: "inspect step 1" });
  await expect(tick1).toBeVisible();
  await tick1.click();
  await expect(page.getByText("Inspector · step 1")).toBeVisible();
  await expect(page.getByText(`operator override ${chosen}`, { exact: false })).toBeVisible();
  // The status strip shows the same badge for the latest step, so scope to the inspector.
  const inspector = page.locator("section", { hasText: "Inspector · step 1" });
  await expect(inspector.getByText(`escalated -> ${chosen}`)).toBeVisible();
  await page.keyboard.press("Escape");

  await page.getByRole("button", { name: "drop work zone ahead" }).click();
  await expect(page.getByText(/work zone · lane 3/)).toBeVisible();
  await expect(page.getByText("checker lane_closed")).toBeVisible();
});

test("the metrics view loads the evaluation report or says how to produce one", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "metrics", exact: true }).click();
  await expect(page.getByText(/violations per episode|No evaluation yet/i).first()).toBeVisible();
  await page.getByRole("button", { name: "console", exact: true }).click();
  await expect(page.getByText("ROAD VIEW", { exact: false })).toBeVisible();
});
