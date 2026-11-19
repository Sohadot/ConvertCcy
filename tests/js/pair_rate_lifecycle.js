// SEO-A3 browser lifecycle checks for /assets/js/pair-rate.js.
// Usage: node tests/js/pair_rate_lifecycle.js <baseUrl> <fmtCasesJson>
// Prints one JSON object with results; exit code 0 always (Python asserts).
const { chromium } = require('playwright');

const base = process.argv[2];
const fmtCases = JSON.parse(process.argv[3] || '[]');
// SEO-A4.6A: no published pair is generic-unsupported, so the Python test passes a synthetic
// unsupported page (built against a snapshot that lacks the code) and that snapshot.
const synthetic = JSON.parse(process.argv[4] || 'null');
const fs = require('fs');

async function open(browser, path, { js = true, live = 'fail', snapshot = null, htmlFile = null } = {}) {
  const ctx = await browser.newContext({ javaScriptEnabled: js });
  const page = await ctx.newPage();
  if (htmlFile) {
    const body = fs.readFileSync(htmlFile, 'utf8');
    await page.route(u => u.pathname === path, r => r.fulfill({ status: 200, contentType: 'text/html', body }));
  }
  await page.route(/googletagmanager|google-analytics|fonts\.(googleapis|gstatic)/, r => r.abort());
  await page.route(/api\.exchangerate-api\.com/, r => {
    if (live === 'fail') return r.abort();
    return r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(live) });
  });
  if (snapshot) {
    await page.route(/\/rates\/snapshot\.json/, r =>
      r.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(snapshot) }));
  }
  // Record every text the rate headline ever shows (detects flashes).
  await page.addInitScript(() => {
    window.__seen = [];
    document.addEventListener('DOMContentLoaded', () => {
      const el = document.getElementById('live-rate');
      if (!el) return;
      window.__seen.push(el.textContent);
      new MutationObserver(() => window.__seen.push(el.textContent))
        .observe(el, { childList: true, characterData: true, subtree: true });
    });
  });
  await page.goto(base + path, { waitUntil: 'load' });
  await page.waitForTimeout(600);
  const out = await page.evaluate(() => ({
    main: (document.getElementById('live-rate') || {}).textContent || '',
    inverse: (document.getElementById('inverse-rate') || {}).textContent || '',
    badge: (document.getElementById('rate-badge') || {}).textContent || '',
    note: (document.getElementById('rate-source') || {}).textContent || '',
    rows: [...document.querySelectorAll('#conv-table tr')].map(tr => [...tr.cells].map(c => c.textContent)),
    toInput: (document.getElementById('to-input') || {}).value || null,
    seen: window.__seen || [],
  }));
  if (js && path.includes('usd-to-eur')) {
    out.fmt = await page.evaluate(cases => cases.map(([v, s]) => window.__convertccyRate.fmt(v, s)), fmtCases);
    await page.fill('#from-input', '100');
    await page.dispatchEvent('#from-input', 'input');
    out.after100 = await page.evaluate(() => document.getElementById('main-result').textContent);
  }
  await ctx.close();
  return out;
}

(async () => {
  const browser = await chromium.launch();
  const res = {};
  res.nojs = await open(browser, '/pages/usd-to-eur.html', { js: false });
  res.liveFail = await open(browser, '/pages/usd-to-eur.html', { live: 'fail' });
  res.liveOk = await open(browser, '/pages/usd-to-eur.html', { live: { base: 'USD', date: '2099-01-02', rates: { EUR: 0.95 } } });
  res.newerSnap = await open(browser, '/pages/usd-to-eur.html', {
    live: 'fail',
    snapshot: { base: 'USD', as_of: '2099-01-01', source: 'exchangerate-api.com', rates: { USD: 1, EUR: 0.5 } },
  });
  if (synthetic) {
    const syn = { htmlFile: synthetic.html_file, snapshot: synthetic.snapshot };
    res.unsupported = await open(browser, '/pages/isk-to-usd.html', { live: 'fail', ...syn });
    res.unsupportedNoJs = await open(browser, '/pages/isk-to-usd.html', { js: false, ...syn });
  }
  res.liveFiat = await open(browser, '/pages/kpw-to-usd.html', { live: 'fail' });
  res.liveFiatNoJs = await open(browser, '/pages/kpw-to-usd.html', { js: false });
  await browser.close();
  console.log(JSON.stringify(res));
})().catch(e => { console.log(JSON.stringify({ error: String(e) })); });
