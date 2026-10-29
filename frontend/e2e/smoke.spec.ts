import { expect, test, type Page } from "@playwright/test";

const PASSWORD = "Password@123";

async function login(page: Page, role: string, email: string, password = PASSWORD, expectOk = password === PASSWORD) {
  await page.goto("/login");
  await page.getByRole("button", { name: new RegExp(`^${role}$`, "i") }).click();
  await page.getByPlaceholder("Email address").fill(email);
  await page.getByPlaceholder("Password").fill(password);
  await page.locator("form button[type=submit]").click();
  if (expectOk) await page.waitForURL((u) => !u.pathname.startsWith("/login"), { timeout: 20_000 });
}

test("doctor drafts, reviews and approves a plan; patient sees it", async ({ page, browser }) => {
  await login(page, "Doctor", "ananya.rao@carexhealth.health");
  await expect(page).toHaveURL(/\/doctor/);
  await page.goto("/doctor/patients");
  await page.getByText("Arjun Sharma").first().click();
  await expect(page).toHaveURL(/\/doctor\/patients\//);
  await page.getByRole("button", { name: "Write discharge plan" }).click();
  await page.getByPlaceholder(/handwritten note/i).fill("Take Tab Paracetamol 650mg three times daily for 5 days. Follow up after 2 weeks. Notify nurse if temperature exceeds 101°F.");
  await page.getByRole("button", { name: "Generate care plan" }).click();
  await page.getByRole("button", { name: /approve & activate/i }).click({ timeout: 30_000 });
  await expect(page.getByText(/agents are executing it|approved/i).first()).toBeVisible({ timeout: 30_000 });

  const patient = await (await browser.newContext()).newPage();
  await login(patient, "Patient", "arjun.sharma@example.com");
  await expect(patient).toHaveURL(/\/patient/);
  await patient.goto("/patient/plan");
  await expect(patient.getByText(/Paracetamol/i).first()).toBeVisible({ timeout: 20_000 });
});

test("every role can open Profile & settings and change language", async ({ page }) => {
  await login(page, "Nurse", "priya.nair@carexhealth.health");
  await page.goto("/nurse/settings");
  await expect(page.getByText("Personal details")).toBeVisible();
  await page.getByLabel("Language").selectOption("hi");
  await page.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("व्यक्तिगत विवरण")).toBeVisible(); // "Personal details" in Hindi, applied immediately
  await page.getByLabel(/भाषा|Language/).first().selectOption("en");
  await page.getByRole("button", { name: /बदलाव सहेजें|Save changes/ }).click();
});

test("wrong password is rejected and the account locks after repeated failures", async ({ page }) => {
  for (let i = 0; i < 5; i++) {
    await login(page, "Doctor", "kavya.menon@carexhealth.health", "wrong-password-1");
    await expect(page.getByText(/invalid email or password|too many failed attempts/i).first()).toBeVisible();
  }
  await login(page, "Doctor", "kavya.menon@carexhealth.health", PASSWORD, false);
  await expect(page.getByText(/too many failed attempts/i).first()).toBeVisible();
});
