import { expect, test, type Page, type Browser } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
async function accessible(page: Page) {
  const result = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa", "wcag21aa"])
    .analyze();
  expect(
    result.violations.map((v) => ({
      id: v.id,
      nodes: v.nodes.map((n) => ({
        target: n.target,
        summary: n.failureSummary,
      })),
    })),
  ).toEqual([]);
}
const password = "browser-fixture-password-2026";
async function login(page: Page, email = "requester@example.com") {
  await page.goto("/login");
  await page.getByLabel("Email address").fill(email);
  await page.getByLabel("Password", { exact: true }).fill(password);
  await page.getByRole("button", { name: "Sign in", exact: true }).click();
  await expect(page.getByRole("heading", { name: /^Welcome,/ })).toBeVisible();
}
async function actor(browser: Browser, email: string) {
  const context = await browser.newContext({
    baseURL: "http://127.0.0.1:3101",
  });
  const page = await context.newPage();
  await login(page, email);
  return { context, page };
}
function documents(company: string, suffix: string, includeBank = true) {
  const docs = [
    {
      name: "tax.txt",
      mimeType: "text/plain",
      buffer: Buffer.from(
        `Tax form\nFictional browser fixture\ncompany_name: ${company}\ntax_id: 91-${suffix}\ncontact_name: Jamie Example\ncontact_email: jamie@example.com`,
      ),
    },
    {
      name: "insurance.txt",
      mimeType: "text/plain",
      buffer: Buffer.from(
        "Insurance certificate\nFictional browser fixture\ninsurance_expiration: 2030-12-31",
      ),
    },
  ];
  if (includeBank)
    docs.push({
      name: "bank.txt",
      mimeType: "text/plain",
      buffer: Buffer.from(
        "Bank confirmation\nFictional browser fixture; no bank account numbers.",
      ),
    });
  return docs;
}
async function submit(
  page: Page,
  company: string,
  suffix: string,
  includeBank = true,
) {
  await page.goto("/requests/new");
  await page.getByLabel("Request title").fill(`${company} onboarding`);
  await page
    .getByLabel("What needs to happen?")
    .fill(
      `Please onboard ${company} as our new vendor. Documents are attached for review.`,
    );
  await page
    .locator('input[type="file"]')
    .setInputFiles(documents(company, suffix, includeBank));
  await page
    .getByRole("button", { name: "Submit request", exact: true })
    .click();
  await expect(page).toHaveURL(/\/workflows\/[a-f0-9-]+$/);
  return page.url();
}

test("request, independent approval, execution, audit, notification and logout", async ({
  page,
  browser,
}, testInfo) => {
  await login(page);
  const url = await submit(page, "Cedar Robotics", "1000001");
  await expect(
    page.getByText("Awaiting approval", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByText("Ready for a decision", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText("••-•••0001", { exact: true })).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Confirm approval", exact: true }),
  ).toHaveCount(0);
  const downloadPromise = page.waitForEvent("download");
  await page.getByRole("link", { name: "Download tax.txt" }).click();
  expect((await downloadPromise).suggestedFilename()).toBe("tax.txt");
  const reviewer = await actor(browser, "approver@example.com");
  await reviewer.page.goto(url);
  await expect(
    reviewer.page.getByRole("button", { name: /^Approve Create/ }),
  ).toBeVisible();
  await accessible(reviewer.page);
  await reviewer.page.screenshot({
    path: testInfo.outputPath("review-desktop.png"),
    fullPage: true,
  });
  await reviewer.page.getByRole("button", { name: /^Approve Create/ }).click();
  await reviewer.page
    .getByLabel("Decision note")
    .fill("Evidence checked; approved for onboarding.");
  await reviewer.page
    .getByRole("button", { name: "Confirm approval", exact: true })
    .click();
  await expect(
    reviewer.page.getByText("Completed", { exact: true }),
  ).toBeVisible();
  await reviewer.page
    .getByRole("button", { name: "Audit trail", exact: true })
    .click();
  await expect(
    reviewer.page.getByText("Page verified", { exact: true }),
  ).toBeVisible();
  await expect(
    reviewer.page.getByText("Create Vendor", { exact: true }),
  ).toBeVisible();
  await expect(
    reviewer.page.getByText("Send Notification", { exact: true }),
  ).toBeVisible();
  await reviewer.page.screenshot({
    path: testInfo.outputPath("audit-desktop.png"),
    fullPage: true,
  });
  await reviewer.context.close();
  await page.goto("/notifications");
  await expect(
    page.getByText("Vendor onboarding completed", { exact: true }),
  ).toBeVisible();
  await page.getByRole("button", { name: "Mark as read" }).first().click();
  await expect(page.getByLabel("Unread")).toHaveCount(0);
  await page.getByRole("button", { name: "Sign out" }).click();
  await expect(page).toHaveURL(/\/login$/);
  await page.goto(url);
  await expect(page).toHaveURL(/\/login$/);
});

test("missing evidence can be revised and reviewers request changes", async ({
  page,
  browser,
}) => {
  await login(page);
  const url = await submit(page, "Juniper Systems", "1000002", false);
  await expect(
    page.getByText("Needs information", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "Revise request", exact: true })
    .click();
  await page
    .getByLabel("Updated request")
    .fill(
      "Please onboard Juniper Systems. The missing bank confirmation is now attached.",
    );
  await page
    .locator('input[type="file"]')
    .setInputFiles(documents("Juniper Systems", "1000002").slice(2));
  await page
    .getByRole("button", { name: "Submit revision", exact: true })
    .click();
  await expect(
    page.getByText("Awaiting approval", { exact: true }),
  ).toBeVisible();
  await expect(page.getByText(/FP-.*Revision 2/)).toBeVisible();
  const reviewer = await actor(browser, "reviewer@example.com");
  await reviewer.page.goto(url);
  await expect(
    reviewer.page.getByRole("button", { name: /^Approve Create/ }),
  ).toHaveCount(0);
  await reviewer.page
    .getByRole("button", { name: /^Request changes Return/ })
    .click();
  await reviewer.page
    .getByLabel("Decision note")
    .fill("Please confirm the primary contact before approval.");
  await reviewer.page
    .getByRole("button", { name: "Confirm changes request" })
    .click();
  await expect(
    reviewer.page.getByText("Needs information", { exact: true }),
  ).toBeVisible();
  await reviewer.context.close();
});

test("own-request approval is disabled and rejection is recorded", async ({
  page,
}) => {
  await login(page, "approver@example.com");
  await submit(page, "Birch Research", "1000003");
  await expect(
    page.getByText("Awaiting approval", { exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole("button", { name: /^Approve Create/ }),
  ).toBeDisabled();
  await page.getByRole("button", { name: /^Reject Close/ }).click();
  await page
    .getByLabel("Decision note")
    .fill("Submitted in error; close this request.");
  await page.getByRole("button", { name: "Confirm rejection" }).click();
  await expect(page.getByText("Rejected", { exact: true })).toBeVisible();
});

test("desktop and mobile overview are accessible; ownership is enforced", async ({
  page,
  browser,
}, testInfo) => {
  await login(page);
  const privateUrl = await submit(page, "Willow Services", "1000004");
  await expect(
    page.getByText("Awaiting approval", { exact: true }),
  ).toBeVisible();
  await page.goto("/");
  await expect(page.getByRole("heading", { name: /^Welcome,/ })).toBeVisible();
  await page.screenshot({
    path: testInfo.outputPath("overview-desktop.png"),
    fullPage: true,
  });
  await accessible(page);
  const other = await actor(browser, "other@example.com");
  await other.page.goto(privateUrl);
  await expect(
    other.page.getByRole("alert").filter({ hasText: "Workflow not found" }),
  ).toBeVisible();
  await expect(
    other.page.getByText("Willow Services", { exact: true }),
  ).toHaveCount(0);
  await other.context.close();
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/");
  await page.getByRole("button", { name: "Open navigation" }).click();
  await page.getByRole("link", { name: "Requests", exact: true }).click();
  await expect(
    page.getByRole("heading", { name: "All requests" }),
  ).toBeVisible();
  await accessible(page);
  const statusCell = page
    .getByRole("table")
    .getByText("Awaiting approval", { exact: true });
  await expect(statusCell).toBeInViewport();
  const overflow = await page.evaluate(() => ({
    width: innerWidth,
    scroll: document.documentElement.scrollWidth,
    elements: Array.from(document.querySelectorAll("body *"))
      .filter((e) => e.getBoundingClientRect().right > innerWidth)
      .map((e) => ({
        tag: e.tagName,
        cls: e.className,
        right: e.getBoundingClientRect().right,
      }))
      .slice(0, 25),
  }));
  expect(overflow, JSON.stringify(overflow)).toMatchObject({
    scroll: overflow.width,
  });
  await page.screenshot({
    path: testInfo.outputPath("requests-mobile.png"),
    fullPage: true,
  });
});

test("administrator creates a real account and updates access", async ({
  page,
}) => {
  await login(page, "admin@example.com");
  await page.getByRole("link", { name: "Team", exact: true }).click();
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .click();
  await page.getByLabel("Full name").fill("Morgan Test");
  await page.getByLabel("Email address").fill("morgan@example.com");
  await page
    .getByLabel("Initial password")
    .fill("new-browser-account-password");
  await page.getByLabel("Role", { exact: true }).selectOption("reviewer");
  await page
    .getByRole("button", { name: "Create account", exact: true })
    .last()
    .click();
  await expect(
    page.getByText("Account created.", { exact: false }),
  ).toBeVisible();
  const row = page.getByRole("row").filter({ hasText: "morgan@example.com" });
  await row.getByRole("checkbox", { name: "Active" }).uncheck();
  await row.getByRole("button", { name: "Save", exact: true }).click();
  await expect(
    page.getByText("Account access updated.", { exact: true }),
  ).toBeVisible();
  await expect(row.getByRole("checkbox", { name: "Active" })).not.toBeChecked();
});

test("a revision draft cannot silently adopt another editor's newer revision", async ({
  page,
  browser,
}) => {
  await login(page);
  const url = await submit(page, "Maple Studio", "1000005", false);
  await expect(
    page.getByText("Needs information", { exact: true }),
  ).toBeVisible();
  // Keep the owner's polling view on revision 1 until the competing edit has finished.
  const endpoint = `/api/workflows/${url.split("/").pop()}`;
  const snapshot = await (await page.request.get(endpoint)).json();
  let hold = true;
  await page.route(`**${endpoint}`, async (route) => {
    if (hold && route.request().method() === "GET")
      await route.fulfill({ json: snapshot });
    else await route.continue();
  });
  await page
    .getByRole("button", { name: "Revise request", exact: true })
    .click();
  await page
    .getByLabel("Updated request")
    .fill("This draft began before another editor changed the request.");
  const admin = await actor(browser, "admin@example.com");
  await admin.page.goto(url);
  await admin.page
    .getByRole("button", { name: "Revise request", exact: true })
    .click();
  await admin.page
    .getByLabel("Updated request")
    .fill(
      "Newer description from the administrator. Bank evidence still pending.",
    );
  await admin.page
    .getByRole("button", { name: "Submit revision", exact: true })
    .click();
  await expect(admin.page.getByText(/FP-.*Revision 2/)).toBeVisible();
  await expect(
    admin.page.getByText("Needs information", { exact: true }),
  ).toBeVisible();
  hold = false;
  await expect(page.getByText(/FP-.*Revision 2/)).toBeVisible();
  await page
    .getByRole("button", { name: "Submit revision", exact: true })
    .click();
  await expect(
    page
      .getByRole("alert")
      .filter({ hasText: "changed while you were editing" }),
  ).toBeVisible();
  expect((await (await page.request.get(endpoint)).json()).revision).toBe(2);
  await admin.context.close();
});

test("configured multipart uploads larger than 10 MiB reach the API intact", async ({
  page,
}) => {
  await login(page);
  await page.goto("/requests/new");
  await page.getByLabel("Request title").fill("Large transport regression");
  await page
    .getByLabel("What needs to happen?")
    .fill("Please review these large fictional supporting documents.");
  const files = Array.from({ length: 15 }, (_, i) => ({
    name: `evidence-${i}.txt`,
    mimeType: "text/plain",
    buffer: Buffer.from(`Fictional evidence ${i}. `.repeat(40000)),
  }));
  await page.locator('input[type="file"]').setInputFiles(files);
  const response = page.waitForResponse(
    (r) =>
      r.url().endsWith("/api/workflows") && r.request().method() === "POST",
  );
  await page
    .getByRole("button", { name: "Submit request", exact: true })
    .click();
  const saved = await response;
  expect(saved.status()).toBe(201);
  const created = await saved.json();
  const detail = await (
    await page.request.get(`/api/workflows/${created.id}`)
  ).json();
  expect(detail.documents).toHaveLength(15);
});

test("login and request forms have accessible labels and contrast", async ({
  page,
}) => {
  await page.goto("/login");
  await expect(
    page.getByRole("button", { name: "Sign in", exact: true }),
  ).toBeEnabled();
  await accessible(page);
  await login(page);
  await page.goto("/requests/new");
  await expect(page.getByLabel("Request title")).toBeVisible();
  await accessible(page);
});
