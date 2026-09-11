// Synthetic browser contract check; requires an already built web/dist and Playwright.
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const { chromium } = require('playwright-core');
const root = path.resolve(__dirname, '../web/dist');
const reportId = '00000000-0000-4000-8000-000000000017';
let role = 'owner', state = 'OPEN', resolution = null, contentType = 'CHAT_MESSAGE';
const calls = [], environmentHeaders = [], errors = [];
let failFirst = true;
const receipt = () => ({ report_id: reportId, content_type: contentType, reason: 'OTHER', status: state, resolution,
  created_at: '2026-09-07T00:00:00Z', updated_at: '2026-09-07T00:00:00Z' });
const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost');
  if (url.pathname.startsWith('/api/')) {
    environmentHeaders.push(req.headers['x-map-environment']);
    res.setHeader('content-type', 'application/json'); res.setHeader('cache-control', 'no-store');
    if (url.pathname === '/api/v1/auth/me') return res.end(JSON.stringify({ username: 'synthetic operator', role }));
    if (url.pathname === '/api/v1/environments') return res.end(JSON.stringify({ environments: ['test'] }));
    if (url.pathname.endsWith('/actions')) {
      let raw = ''; for await (const part of req) raw += part;
      calls.push(JSON.parse(raw));
      if (failFirst) { failFirst = false; res.statusCode = 503; return res.end(JSON.stringify({ detail: '결과를 확인하고 다시 시도해주세요.' })); }
      state = 'ACTIONED'; resolution = calls.at(-1).action;
      return res.end(JSON.stringify(receipt()));
    }
    if (url.pathname.endsWith('/' + reportId)) return res.end(JSON.stringify({ report: receipt(), description: 'Synthetic report description', current_message: '<img src=x onerror="window.moderationXss=true">', actions: [] }));
    if (url.pathname === '/api/v1/moderation/reports') return res.end(JSON.stringify(state === url.searchParams.get('status') ? [receipt()] : []));
    res.statusCode = 404; return res.end('{}');
  }
  let target = path.join(root, url.pathname);
  if (!target.startsWith(root) || !fs.existsSync(target) || fs.statSync(target).isDirectory()) target = path.join(root, 'index.html');
  res.setHeader('content-type', target.endsWith('.js') ? 'text/javascript' : target.endsWith('.css') ? 'text/css' : 'text/html');
  res.end(fs.readFileSync(target));
});
(async () => {
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve));
  const browser = await chromium.launch({ executablePath: process.env.MAP_TEST_BROWSER || '/Users/ryujemu/Library/Caches/ms-playwright/chromium_headless_shell-1234/chrome-headless-shell-mac-arm64/chrome-headless-shell', headless: true });
  const url = `http://127.0.0.1:${server.address().port}/moderation`;
  const page = await browser.newPage({ viewport: { width: 1400, height: 1100 } });
  page.on('pageerror', error => errors.push(error.name));
  try {
    await page.goto(url);
    await page.getByRole('button', { name: '검토 열기', exact: true }).click();
    await page.getByText('Synthetic report description', { exact: true }).waitFor();
    assert.equal(await page.evaluate(() => window.moderationXss), undefined);
    await page.getByRole('button', { name: '이 메시지 숨김', exact: true }).click();
    await page.getByRole('alert').getByText(/test/).waitFor();
    assert.equal(calls.length, 0);
    await page.getByRole('button', { name: '확인 후 실행', exact: true }).click();
    await page.getByText('결과를 확인하고 다시 시도해주세요.', { exact: true }).waitFor();
    await page.getByRole('button', { name: '확인 후 실행', exact: true }).click();
    await page.getByText('현재 상태: 조치 완료 / HIDE_CHAT_MESSAGE', { exact: true }).waitFor();
    assert.equal(calls.length, 2); assert.equal(calls[0].action_id, calls[1].action_id);
    assert.equal(calls[0].action, 'HIDE_CHAT_MESSAGE');
    await page.screenshot({ path: process.env.MAP_MODERATION_SCREENSHOT || '/tmp/map-admin-moderation-synthetic-20260906.png', fullPage: true });
    await page.getByRole('button', { name: '원문 닫기', exact: true }).click();
    await page.getByText('Synthetic report description', { exact: true }).waitFor({ state: 'detached' });
    role = 'viewer'; state = 'OPEN'; resolution = null;
    await page.reload(); await page.getByRole('cell', { name: '검토 권한 필요', exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: '검토 열기', exact: true }).count(), 0);
    assert.equal(await page.getByText('Synthetic report description', { exact: true }).count(), 0);
    role = 'operator'; await page.reload();
    await page.getByRole('button', { name: '검토 열기', exact: true }).click();
    await page.getByText('Synthetic report description', { exact: true }).waitFor();
    assert.equal(await page.getByRole('button', { name: '이 메시지 숨김', exact: true }).count(), 0);
    assert.equal(await page.getByRole('button', { name: '발신자 채팅 전송 제한', exact: true }).count(), 0);
    assert.equal(await page.getByRole('button', { name: '검토 시작', exact: true }).count(), 1);
    role = 'owner'; state = 'OPEN'; resolution = null; contentType = 'REVIEW_SUMMARY';
    await page.reload();
    await page.getByRole('cell', { name: '리뷰 요약', exact: true }).waitFor();
    await page.getByRole('button', { name: '검토 열기', exact: true }).click();
    await page.getByText(/실제 생성 원문이나 작성자를 검증한 기록이 아닙니다/).waitFor();
    assert.equal(await page.getByRole('button', { name: '이 메시지 숨김', exact: true }).count(), 0);
    assert.equal(await page.getByRole('button', { name: '발신자 채팅 전송 제한', exact: true }).count(), 0);
    assert.equal(await page.getByRole('button', { name: '검토 시작', exact: true }).count(), 1);
    await page.getByRole('button', { name: '대응 완료', exact: true }).click();
    await page.getByRole('button', { name: '확인 후 실행', exact: true }).click();
    await page.getByText('현재 상태: 조치 완료 / RESOLVE', { exact: true }).waitFor();
    assert.equal(calls.at(-1).action, 'RESOLVE');
    assert(environmentHeaders.every(value => value === 'test')); assert.deepEqual(errors, []);
    console.log(JSON.stringify({ result: 'passed', checks: ['owner review', 'escaped content', 'explicit environment', 'confirmation before mutation', 'same UUID on retry', 'updated outcome', 'close clears original', 'viewer metadata only', 'operator no enforcement', 'review summary reporter explanation', 'summary owner cannot hide or restrict', 'summary resolved', 'no browser errors'], backend: 'synthetic HTTP fixture', request_count: environmentHeaders.length }));
  } finally { await browser.close(); await new Promise(resolve => server.close(resolve)); }
})().catch(error => { console.error(JSON.stringify({ result: 'failed', cause: error.name, detail: error.message })); process.exitCode = 1; server.close(); });
