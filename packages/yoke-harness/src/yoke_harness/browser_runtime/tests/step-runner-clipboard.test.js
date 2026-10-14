'use strict';

/**
 * grant_clipboard lets a page write the clipboard, and refuses otherwise.
 *
 * Run: node tests/step-runner-clipboard.test.js
 */

const http = require('http');
const { chromium } = require('playwright');
const { executeStep } = require('../src/step-runner');
const { executeGrantClipboard } = require('../src/step-actions/permissions');

let testCount = 0;
let passCount = 0;
let failCount = 0;

function assert(condition, message) {
  testCount++;
  if (condition) {
    passCount++;
    console.log(`  PASS: ${message}`);
  } else {
    failCount++;
    console.log(`  FAIL: ${message}`);
  }
}

function assertEqual(actual, expected, message) {
  testCount++;
  if (actual === expected) {
    passCount++;
    console.log(`  PASS: ${message}`);
  } else {
    failCount++;
    console.log(
      `  FAIL: ${message} (expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)})`
    );
  }
}

function listen() {
  return new Promise((resolve, reject) => {
    const server = http.createServer((_req, res) => {
      res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' });
      res.end('<!doctype html><title>clipboard</title><p id="copy">copy</p>');
    });
    server.listen(0, '127.0.0.1', () => resolve(server));
    server.on('error', reject);
  });
}

async function testWriteSucceedsAfterGrant() {
  console.log('\n## Test: clipboard write succeeds after grant_clipboard');
  const server = await listen();
  const { port } = server.address();
  const origin = `http://127.0.0.1:${port}`;
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    await page.goto(`${origin}/`, { waitUntil: 'domcontentloaded' });
    const granted = await executeStep(page, {
      action: 'grant_clipboard',
    }, { baseUrl: origin });
    assertEqual(granted.success, true, 'grant_clipboard succeeds on http');
    const written = await page.evaluate(async () => {
      await navigator.clipboard.writeText('yoke-clipboard');
      return navigator.clipboard.readText();
    });
    assertEqual(written, 'yoke-clipboard', 'navigator.clipboard.writeText succeeds');
    await page.close();
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
}

async function testNonHttpOriginIsRefused() {
  console.log('\n## Test: grant_clipboard refuses a non-http page');
  const browser = await chromium.launch({ headless: true });
  try {
    const page = await browser.newPage();
    const result = await executeStep(page, {
      action: 'grant_clipboard',
    }, { baseUrl: 'https://example.com' });
    assertEqual(result.success, false, 'about:blank is refused');
    assert(
      (result.error || '').includes('clipboard_permission_origin_required'),
      'refusal names clipboard_permission_origin_required'
    );
    assert(
      (result.error || '').includes('Navigate to the http or https page'),
      'refusal names the recovery'
    );
    await page.close();
  } finally {
    await browser.close();
  }
}

async function testOtherBrowserIsRefused() {
  console.log('\n## Test: grant_clipboard refuses a non-chromium surface');
  const page = {
    url: () => 'https://example.com/hero',
    context: () => ({
      browser: () => ({ browserType: () => ({ name: () => 'firefox' }) }),
      grantPermissions: async () => {
        throw new Error('grantPermissions should not run');
      },
    }),
  };
  let caught = null;
  try {
    await executeGrantClipboard(page);
  } catch (err) {
    caught = err;
  }
  assert(caught !== null, 'firefox is refused');
  assert(
    caught && caught.message.includes('clipboard_permission_unsupported'),
    'refusal names clipboard_permission_unsupported'
  );
  assert(
    caught && caught.message.includes('yoke qa browser setup'),
    'refusal names the Chromium recovery'
  );
}

async function run() {
  console.log('=== Step Runner Tests: Clipboard ===');
  try {
    await testWriteSucceedsAfterGrant();
    await testNonHttpOriginIsRefused();
    await testOtherBrowserIsRefused();
  } catch (err) {
    console.error('\nUnexpected error:', err);
    failCount++;
  }
  console.log(`\n=== Results: ${passCount}/${testCount} passed, ${failCount} failed ===`);
  if (failCount > 0) process.exit(1);
}

run();
