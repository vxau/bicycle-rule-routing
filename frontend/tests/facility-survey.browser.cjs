// Optional smoke test: requires Playwright and Chromium, plus the synthetic server.
const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || '/usr/bin/chromium', headless: true,
    args: ['--no-sandbox'],
  });
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
    page.setDefaultTimeout(10000);
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    // OSM names are untrusted text, including in Leaflet's hover tooltip.
    await page.route('**/api/facilities', async route => {
      const response = await route.fetch();
      const data = await response.json();
      data.features.find(f => f.properties.segment_id === '2|3|0').properties.name =
        '<img src=x onerror="window.__surveyXss=1">';
      await route.fulfill({ response, json: data });
    });
    if (process.env.LEAFLET_ASSET_DIR) {
      for (const file of ['leaflet.js', 'leaflet.css']) {
        await page.route(`https://unpkg.com/leaflet@1.9.4/dist/${file}`, route => route.fulfill({
          path: path.join(process.env.LEAFLET_ASSET_DIR, file),
          contentType: file.endsWith('.js') ? 'text/javascript' : 'text/css',
        }));
      }
    }
    await page.route('https://tile.openstreetmap.org/**', route => route.abort());
    await page.goto(process.env.SURVEY_TEST_URL || 'http://127.0.0.1:8001/');
    await page.getByLabel('設備調査', { exact: true }).check({ timeout: 5000 });
    await page.locator('#survey-status').filter({ hasText: '5区間' }).waitFor();
    assert.equal(await page.locator('path.facility-road').count(), 5);
    await page.getByLabel('設備あり', { exact: true }).uncheck();
    await page.getByLabel('明示的になし', { exact: true }).uncheck();
    assert.equal(await page.locator('path.facility-road').count(), 2);
    // A horizontal SVG line has a zero-height box; click a painted dash on the real path.
    const roadPoint = await page.locator('path[data-segment-id="2|3|0"]').evaluate(path => {
      const point = path.getPointAtLength(2);
      const screen = new DOMPoint(point.x, point.y).matrixTransform(path.getScreenCTM());
      return { x: screen.x, y: screen.y };
    });
    await page.mouse.move(roadPoint.x, roadPoint.y);
    await page.locator('.leaflet-tooltip').waitFor();
    assert.equal(await page.locator('.leaflet-tooltip img').count(), 0, 'road names must not create HTML');
    assert.ok((await page.locator('.leaflet-tooltip').innerText()).includes('<img src=x'));
    assert.equal(await page.evaluate(() => window.__surveyXss), undefined);
    await page.mouse.click(roadPoint.x, roadPoint.y);
    await page.getByRole('button', { name: '調査リストに追加', exact: true }).click();
    assert.equal(await page.locator('#survey-selected-list li').count(), 1);
    assert.equal(await page.locator('#route-status').innerText(), '出発地を選択');

    await page.reload();
    await page.getByLabel('設備調査', { exact: true }).check();
    await page.locator('#survey-selected-list li').waitFor();
    assert.equal(await page.locator('#survey-selected-list li').count(), 1);
    const downloadReady = page.waitForEvent('download');
    await page.getByRole('button', { name: '調査CSVを保存', exact: true }).click();
    const download = await downloadReady;
    const csv = await fs.readFile(await download.path(), 'utf8');
    assert.ok(csv.startsWith('\uFEFF'));
    assert.ok(csv.includes('"2|3|0"'));
    assert.ok(csv.includes('"確認結果"'));

    await page.getByLabel('経路比較', { exact: true }).check();
    assert.equal(await page.locator('path.facility-road').count(), 0);
    await page.getByLabel('整備候補', { exact: true }).uncheck();
    // Real pointer clicks select endpoints; the existing API computes all five profiles.
    for (const longitude of [139, 139.005]) {
      const point = await page.evaluate(longitude => {
        const p = map.latLngToContainerPoint([35, longitude]);
        const box = document.querySelector('#map').getBoundingClientRect();
        return { x: box.left + p.x, y: box.top + p.y };
      }, longitude);
      await page.mouse.click(point.x, point.y);
    }
    await page.locator('#route-status').filter({ hasText: '5ルート表示' }).waitFor();
    assert.equal(await page.locator('#route-comparison-body tr').count(), 5);
    await page.getByLabel('設備調査', { exact: true }).check();
    assert.equal(await page.locator('.route-panel').isVisible(), false);
    await page.getByRole('button', { name: '調査リストから削除', exact: true }).click();
    assert.equal(await page.locator('#survey-selected-list li').count(), 0);
    assert.equal(await page.getByRole('button', { name: '調査CSVを保存', exact: true }).isDisabled(), true);

    if (process.env.SURVEY_SCREENSHOT_DIR) {
      await fs.mkdir(process.env.SURVEY_SCREENSHOT_DIR, { recursive: true });
      await page.screenshot({ path: path.join(process.env.SURVEY_SCREENSHOT_DIR, 'desktop.png'), fullPage: true });
    }

    await page.setViewportSize({ width: 390, height: 844 });
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth), false);
    if (process.env.SURVEY_SCREENSHOT_DIR) {
      await page.screenshot({ path: path.join(process.env.SURVEY_SCREENSHOT_DIR, 'mobile.png'), fullPage: true });
    }
    await page.route('**/api/facilities', route => route.fulfill({
      status: 503, contentType: 'application/json', body: JSON.stringify({ detail: '道路グラフがありません' }),
    }));
    await page.reload();
    await page.getByLabel('設備調査', { exact: true }).check();
    await page.locator('#survey-status').filter({ hasText: '道路グラフがありません' }).waitFor();
    assert.equal(await page.getByRole('button', { name: '調査CSVを保存', exact: true }).isDisabled(), true);
    assert.deepEqual(errors, []);
    console.log('Browser smoke passed: filters, details, selection, persistence, CSV, modes, mobile, missing data.');
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
