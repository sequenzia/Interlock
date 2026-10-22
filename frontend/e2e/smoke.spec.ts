import { expect, test } from "@playwright/test";

test("console connects, a rule escalates in mock mode, the operator resolves it, the inspector opens", async ({ page }) => {
  await page.goto("/");
  await expect(page.getByText("INTERLOCK")).toBeVisible();
  await expect(page.getByText("jev mock")).toBeVisible();
  // The idle queue also says "no rules yet", so match the rules panel's own sentence.
  await expect(page.getByText("The agent drives on task reward alone", { exact: false })).toBeVisible();

  await page.getByRole("button", { name: "+ Speed limit 25 m/s" }).click();
  // The checker name sits in the tooltip of the "scored" tag.
  await expect(page.getByTitle("checker speed_limit")).toBeVisible();

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
  // The road view HUD repeats the operator's answer for the step on screen, so scope to the inspector.
  const inspector0 = page.locator("section", { hasText: "Inspector · step 0" });
  await expect(inspector0).toBeVisible();
  await expect(inspector0.getByText("operator deny", { exact: false })).toBeVisible();
  await expect(inspector0.getByText("no compliant action", { exact: false })).toBeVisible();
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
  const inspector1 = page.locator("section", { hasText: "Inspector · step 1" });
  await expect(inspector1).toBeVisible();
  await expect(inspector1.getByText(`operator override ${chosen}`, { exact: false })).toBeVisible();
  // The badge reads "escalated → <action>"; the arrow sits in its own span.
  await expect(inspector1.getByText(new RegExp(`escalated\\s*→\\s*${chosen}`))).toBeVisible();
  await page.keyboard.press("Escape");

  await page.getByRole("button", { name: "drop work zone ahead" }).click();
  await expect(page.getByText(/work zone · lane 3/)).toBeVisible();
  await expect(page.getByTitle("checker lane_closed")).toBeVisible();
});

test("the metrics view loads the evaluation report or says how to produce one", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "metrics" }).click();
  await expect(page.getByText(/violations per episode|No evaluation yet/i).first()).toBeVisible();
  const source = page.getByRole("combobox", { name: "source: live or a logged run" });
  await expect(source).toHaveCount(0);
  await page.getByRole("tab", { name: "console" }).click();
  await expect(page.getByText("ROAD VIEW", { exact: false })).toBeVisible();
  await expect(source).toBeVisible();
});

test("the shortcuts overlay opens with ? and the density toggle scales the root", async ({ page }) => {
  await page.goto("/");
  await page.keyboard.press("?");
  await expect(page.getByRole("dialog", { name: "keyboard shortcuts" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog", { name: "keyboard shortcuts" })).toHaveCount(0);

  const talk = page.getByRole("button", { name: "Aa" });
  await talk.click();
  await expect(page.locator("html")).toHaveAttribute("data-density", "talk");
  await talk.click();
  await expect(page.locator("html")).toHaveAttribute("data-density", "normal");
});
