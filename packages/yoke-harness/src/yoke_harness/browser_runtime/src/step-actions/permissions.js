'use strict';

/**
 * Permission grants a scenario step can apply to the open page.
 *
 * Clipboard is granted for the page origin through Playwright's permission
 * API. Chromium honours clipboard-read and clipboard-write. Any other
 * browser, and any page that is not http or https, is refused by name.
 */

const CLIPBOARD_PERMISSIONS = Object.freeze([
  'clipboard-read',
  'clipboard-write',
]);

const ORIGIN_REQUIRED = 'clipboard_permission_origin_required';
const UNSUPPORTED = 'clipboard_permission_unsupported';

/**
 * @param {import('playwright').Page} page
 * @returns {string}
 */
function pageHttpOrigin(page) {
  let parsed = null;
  try {
    parsed = new URL(page.url());
  } catch (_) {
    parsed = null;
  }
  if (!parsed || (parsed.protocol !== 'http:' && parsed.protocol !== 'https:')) {
    const shown = parsed ? parsed.protocol : 'unreadable';
    throw new Error(
      `${ORIGIN_REQUIRED}: grant_clipboard applies to the open page's http `
      + `or https origin, and this page is ${shown}. Navigate to the http or `
      + 'https page, then run grant_clipboard again.'
    );
  }
  return parsed.origin;
}

/**
 * @param {import('playwright').BrowserContext} context
 * @returns {string}
 */
function browserName(context) {
  if (!context || typeof context.browser !== 'function') {
    return '';
  }
  const browser = context.browser();
  if (!browser || typeof browser.browserType !== 'function') {
    return '';
  }
  const type = browser.browserType();
  return type && typeof type.name === 'function' ? type.name() : '';
}

function unsupported(detail) {
  return new Error(
    `${UNSUPPORTED}: ${detail} Use the Chromium runtime from `
    + '`yoke qa browser setup`, open the http or https page, and run '
    + 'grant_clipboard again.'
  );
}

/**
 * Grant clipboard-read and clipboard-write for the open page's origin.
 *
 * @param {import('playwright').Page} page
 * @returns {Promise<{success: true}>}
 */
async function executeGrantClipboard(page) {
  const origin = pageHttpOrigin(page);
  const context = page.context();
  if (!context || typeof context.grantPermissions !== 'function') {
    throw unsupported(
      'this browser surface has no permission grant.'
    );
  }
  const name = browserName(context);
  if (name && name !== 'chromium') {
    throw unsupported(
      `${name} cannot grant clipboard-read and clipboard-write.`
    );
  }
  try {
    await context.grantPermissions(CLIPBOARD_PERMISSIONS, { origin });
  } catch (err) {
    const detail = err && err.message ? err.message : String(err);
    throw unsupported(
      `the browser refused clipboard-read and clipboard-write for ${origin} `
      + `(${detail}).`
    );
  }
  return { success: true };
}

module.exports = {
  executeGrantClipboard,
};
