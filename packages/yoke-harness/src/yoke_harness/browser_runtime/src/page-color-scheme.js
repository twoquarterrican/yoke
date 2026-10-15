'use strict';

// A page's declared preference is fixed for its owner, never a context default.
const preferences = new WeakMap();

function validateColorScheme(value) {
  if (value !== undefined && value !== 'light' && value !== 'dark') {
    throw new Error('case_color_scheme_invalid: colorScheme must be light or dark; '
      + 'correct it or omit the key for the ordinary browser preference.');
  }
}

async function observeColorScheme(page) {
  let observed;
  try {
    const read = () => page.evaluate(() => {
      if (matchMedia('(prefers-color-scheme: dark)').matches) return 'dark';
      if (matchMedia('(prefers-color-scheme: light)').matches) return 'light';
      return null;
    });
    const deadline = performance.now() + 5000;
    for (;;) {
      try {
        observed = await read();
        break;
      } catch (err) {
        const remaining = deadline - performance.now();
        if (remaining <= 0 || !/Execution context was destroyed|Cannot find context with specified id/.test(err.message)) throw err;
        // Load state may still describe the old document during replacement.
        // Re-read only the media preference, under the same deadline.
        await page.waitForLoadState('domcontentloaded', { timeout: remaining });
      }
    }
  } catch (err) {
    throw new Error('color_scheme_observation_failed: cannot read page media preference; '
      + `inspect the existing page and retained evidence before repair; do not replay a submit blindly (${err.message}).`);
  }
  const requested = preferences.get(page) ?? null;
  const evidence = { requested, observed };
  if (requested !== null && observed !== requested) {
    const error = new Error(`color_scheme_mismatch: requested ${requested}, observed ${observed}; `
      + 'reopen the case page with its declared preference and rerun.');
    error.color_scheme = evidence;
    throw error;
  }
  return evidence;
}

async function applyColorScheme(page, requested) {
  validateColorScheme(requested);
  const previous = preferences.get(page);
  if (preferences.has(page) && previous !== requested) {
    throw new Error('color_scheme_owner_conflict: a resumed page has a different '
      + 'declared preference; close it and start a new case page.');
  }
  if (requested !== undefined) {
    try {
      await page.emulateMedia({ colorScheme: requested });
    } catch (err) {
      throw new Error('color_scheme_emulation_failed: cannot apply page preference; '
        + `inspect the existing page and retained evidence before repair; do not replay a submit blindly (${err.message}).`);
    }
  }
  preferences.set(page, requested);
  return observeColorScheme(page);
}

module.exports = { applyColorScheme, observeColorScheme, validateColorScheme };
