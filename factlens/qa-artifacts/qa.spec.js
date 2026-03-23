const { test, expect } = require('playwright/test');

const APP_URL = 'http://127.0.0.1:5173';

async function collectLayoutState(page) {
  return page.evaluate(() => {
    const viewportWidth = window.innerWidth;
    const viewportHeight = window.innerHeight;
    const root = document.documentElement;
    const overflowX = root.scrollWidth - viewportWidth;

    const offenders = Array.from(document.querySelectorAll('body *'))
      .map((node) => {
        const rect = node.getBoundingClientRect();
        if (!rect.width || !rect.height) {
          return null;
        }

        const text = (node.textContent || '').trim().replace(/\s+/g, ' ').slice(0, 80);
        if (rect.left < -1 || rect.right > viewportWidth + 1) {
          return {
            tag: node.tagName.toLowerCase(),
            left: Math.round(rect.left),
            right: Math.round(rect.right),
            width: Math.round(rect.width),
            text,
          };
        }
        return null;
      })
      .filter(Boolean)
      .slice(0, 15);

    return {
      viewportWidth,
      viewportHeight,
      scrollWidth: root.scrollWidth,
      scrollHeight: root.scrollHeight,
      overflowX,
      offenders,
    };
  });
}

async function capturePage(page, name) {
  await page.screenshot({
    path: `qa-artifacts/screenshots/${name}.png`,
    fullPage: true,
  });
}

function attachConsoleTracking(page, bucket) {
  page.on('console', (message) => {
    const type = message.type();
    if (type === 'error') {
      bucket.consoleErrors.push(message.text());
    }
  });

  page.on('pageerror', (error) => {
    bucket.pageErrors.push(String(error));
  });
}

test.describe.configure({ mode: 'serial' });

test('FactLens QA pass', async ({ browser }) => {
  const summary = {
    consoleErrors: [],
    pageErrors: [],
    layout: {},
    checks: {},
  };

  const desktop = await browser.newContext({
    viewport: { width: 1440, height: 1600 },
  });
  const page = await desktop.newPage();
  attachConsoleTracking(page, summary);

  await page.goto(APP_URL, { waitUntil: 'networkidle' });
  await expect(page.getByRole('heading', { name: /turn any text into an evidence-backed claim report/i })).toBeVisible();
  summary.layout.homeDesktop = await collectLayoutState(page);
  await capturePage(page, 'home-desktop');
  summary.checks.homeSampleCount = await page.locator('text=Try a sample').locator('..').getByRole('button').count();

  await page.getByRole('button', { name: /clean truth pack/i }).click();
  await page.waitForURL(/\/workspace$/);
  await expect(page.getByRole('heading', { name: /run a new verification pass/i })).toBeVisible();
  await expect(page.getByPlaceholder(/paste an article, transcript, or social post/i)).toHaveValue(/Pacific Ocean/);
  summary.layout.workspacePrefillDesktop = await collectLayoutState(page);
  await capturePage(page, 'workspace-prefill-desktop');

  await page.getByRole('button', { name: /review claims first/i }).click();
  await expect(page.getByRole('heading', { name: /edit the extracted claims before verification/i })).toBeVisible({ timeout: 120000 });
  summary.checks.reviewClaimCount = await page.locator('article').filter({ hasText: /^Claim \d+/ }).count();
  summary.layout.claimReviewDesktop = await collectLayoutState(page);
  await capturePage(page, 'claim-review-desktop');

  await page.getByRole('button', { name: /add claim/i }).click();
  await expect(page.getByText(/claim 4/i)).toBeVisible();
  await page.getByRole('button', { name: /discard draft/i }).click();
  await expect(page.getByRole('heading', { name: /edit the extracted claims before verification/i })).toHaveCount(0);

  await page.getByRole('button', { name: /review claims first/i }).click();
  await expect(page.getByRole('heading', { name: /edit the extracted claims before verification/i })).toBeVisible({ timeout: 120000 });
  await page.getByRole('button', { name: /verify reviewed claims/i }).click();
  await page.waitForURL(/\/report\//, { timeout: 180000 });
  await expect(page.getByText(/deep review view/i)).toBeVisible({ timeout: 120000 });
  summary.layout.reportDesktop = await collectLayoutState(page);
  await capturePage(page, 'report-desktop');

  const reportUrl = page.url();
  const reportId = reportUrl.split('/report/')[1].split('?')[0];
  summary.checks.reportId = reportId;
  summary.checks.reportHasJsonExport = await page.getByRole('link', { name: /^json$/i }).count();
  summary.checks.reportHasPdfExport = await page.getByRole('link', { name: /^pdf$/i }).count();
  summary.checks.reportHasShare = await page.getByRole('button', { name: /share report|copy share link|link copied/i }).count();

  await page.getByRole('button', { name: /pin|unpin/i }).click();
  await expect(page.getByRole('button', { name: /unpin|pin/i })).toBeVisible();
  await page.getByRole('button', { name: /archive|restore/i }).click();
  await expect(page.getByRole('button', { name: /restore/i })).toBeVisible();
  await page.getByRole('button', { name: /archive|restore/i }).click();
  await expect(page.getByRole('button', { name: /archive/i })).toBeVisible();

  await page.goto(`${APP_URL}/history`, { waitUntil: 'networkidle' });
  await expect(page.getByRole('heading', { name: /saved analyses/i })).toBeVisible();
  summary.layout.historyDesktop = await collectLayoutState(page);
  await capturePage(page, 'history-desktop');
  summary.checks.historyCardCount = await page.locator('text=Reuse input').count();

  await page.goto(`${APP_URL}/demo`, { waitUntil: 'networkidle' });
  await expect(page.getByRole('heading', { name: /hackathon walkthrough deck/i })).toBeVisible();
  summary.layout.demoDesktop = await collectLayoutState(page);
  await capturePage(page, 'demo-desktop');

  await page.goto(`${APP_URL}/methodology`, { waitUntil: 'networkidle' });
  await expect(page.getByRole('heading', { name: /how factlens reaches a verdict/i })).toBeVisible();
  summary.layout.methodologyDesktop = await collectLayoutState(page);
  await capturePage(page, 'methodology-desktop');

  await page.goto(`${APP_URL}/workspace`, { waitUntil: 'networkidle' });
  await page.getByRole('button', { name: /enter url/i }).click();
  await page.getByPlaceholder(/https:\/\/example.com\/article/i).fill('https://en.wikipedia.org/wiki/Paris');
  await page.getByRole('button', { name: /review claims first/i }).click();
  await expect(page.getByRole('heading', { name: /edit the extracted claims before verification/i })).toBeVisible({ timeout: 180000 });
  summary.layout.urlClaimReviewDesktop = await collectLayoutState(page);
  await capturePage(page, 'url-claim-review-desktop');
  summary.checks.urlDraftClaimCount = await page.locator('article').filter({ hasText: /^Claim \d+/ }).count();

  await desktop.close();

  const mobile = await browser.newContext({
    viewport: { width: 390, height: 844 },
    isMobile: true,
  });
  const mobilePage = await mobile.newPage();
  attachConsoleTracking(mobilePage, summary);

  await mobilePage.goto(APP_URL, { waitUntil: 'networkidle' });
  summary.layout.homeMobile = await collectLayoutState(mobilePage);
  await capturePage(mobilePage, 'home-mobile');

  await mobilePage.goto(`${APP_URL}/workspace`, { waitUntil: 'networkidle' });
  summary.layout.workspaceMobile = await collectLayoutState(mobilePage);
  await capturePage(mobilePage, 'workspace-mobile');

  await mobilePage.goto(`${APP_URL}/report/${summary.checks.reportId}`, { waitUntil: 'networkidle' });
  summary.layout.reportMobile = await collectLayoutState(mobilePage);
  await capturePage(mobilePage, 'report-mobile');

  await mobilePage.goto(`${APP_URL}/history`, { waitUntil: 'networkidle' });
  summary.layout.historyMobile = await collectLayoutState(mobilePage);
  await capturePage(mobilePage, 'history-mobile');

  await mobile.close();

  const fs = require('fs');
  fs.mkdirSync('qa-artifacts/results', { recursive: true });
  fs.writeFileSync('qa-artifacts/results/summary.json', JSON.stringify(summary, null, 2));

  expect(summary.consoleErrors, `Console errors: ${summary.consoleErrors.join('\n')}`).toEqual([]);
  expect(summary.pageErrors, `Page errors: ${summary.pageErrors.join('\n')}`).toEqual([]);
});
