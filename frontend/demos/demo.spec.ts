import { test, expect } from "@playwright/test";

test("record independent vendor approval and audit", async ({
  browser,
}, testInfo) => {
  const context = await browser.newContext({
    viewport: { width: 1280, height: 850 },
    recordVideo: {
      dir: testInfo.outputPath("recording"),
      size: { width: 1280, height: 850 },
    },
  });
  const page = await context.newPage();
  const video = page.video()!;
  const pause = () => page.waitForTimeout(1600); // Presentation pacing after readiness assertions.
  async function login(email: string) {
    await page.goto("http://127.0.0.1:3101/login");
    await page.getByLabel("Email address").fill(email);
    await page
      .getByLabel("Password", { exact: true })
      .fill("browser-fixture-password-2026");
    await page.getByRole("button", { name: "Sign in", exact: true }).click();
    await expect(
      page.getByRole("heading", { name: /^Welcome,/ }),
    ).toBeVisible();
  }
  try {
    await login("requester@example.com");
    await page.goto("http://127.0.0.1:3101/requests/new");
    await page.getByLabel("Request title").fill("Cedar Robotics onboarding");
    await page
      .getByLabel("What needs to happen?")
      .pressSequentially(
        "Please onboard Cedar Robotics as our new vendor. Evidence is attached for independent review.",
        { delay: 20 },
      );
    await page.locator('input[type="file"]').setInputFiles([
      {
        name: "tax.txt",
        mimeType: "text/plain",
        buffer: Buffer.from(
          "Tax form\nFictional demo fixture\ncompany_name: Cedar Robotics\ntax_id: 91-1000042\ncontact_name: Jamie Example\ncontact_email: jamie@example.com",
        ),
      },
      {
        name: "insurance.txt",
        mimeType: "text/plain",
        buffer: Buffer.from(
          "Insurance certificate\nFictional demo fixture\ninsurance_expiration: 2030-12-31",
        ),
      },
      {
        name: "bank.txt",
        mimeType: "text/plain",
        buffer: Buffer.from(
          "Bank confirmation\nFictional demo fixture; no bank account numbers.",
        ),
      },
    ]);
    await pause();
    await page
      .getByRole("button", { name: "Submit request", exact: true })
      .click();
    await expect(
      page.getByText("Awaiting approval", { exact: true }),
    ).toBeVisible();
    const workflowUrl = page.url();
    await expect(
      page.getByText("Ready for a decision", { exact: true }),
    ).toBeVisible();
    await pause();
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login$/);
    await login("approver@example.com");
    await page.goto(workflowUrl);
    await expect(
      page.getByText("The policy checks passed for this revision.", {
        exact: false,
      }),
    ).toBeVisible();
    await page
      .getByRole("heading", { name: "AI review brief", exact: true })
      .scrollIntoViewIfNeeded();
    await pause();
    await page.getByRole("button", { name: /^Approve Create/ }).click();
    await page
      .getByLabel("Decision note")
      .fill("Evidence checked. Approved for onboarding.");
    await pause();
    await page
      .getByRole("button", { name: "Confirm approval", exact: true })
      .click();
    await expect(page.getByText("Completed", { exact: true })).toBeVisible();
    await pause();
    await page
      .getByRole("button", { name: "Audit trail", exact: true })
      .click();
    await expect(
      page.getByText("Page verified", { exact: true }),
    ).toBeVisible();
    await expect(
      page.getByText("Create Vendor", { exact: true }),
    ).toBeVisible();
    await page
      .getByText("Create Vendor", { exact: true })
      .scrollIntoViewIfNeeded();
    await pause();
    await page.getByRole("button", { name: "Sign out" }).click();
    await expect(page).toHaveURL(/\/login$/);
    await login("requester@example.com");
    await page.goto("http://127.0.0.1:3101/notifications");
    await expect(
      page.getByText("Vendor onboarding completed", { exact: true }),
    ).toBeVisible();
    await pause();
  } finally {
    await context.close();
  }
  await video.saveAs(testInfo.outputPath("demo.webm"));
});
