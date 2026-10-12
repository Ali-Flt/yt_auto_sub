import { mkdirSync, readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { chromium } from 'playwright';

const USER_SCRIPT = resolve(
  process.argv[2] ?? '../youtube-webos/dist/webOSUserScripts/userScript.js'
);
const VIDEO_ID = process.argv[3] ?? 'dQw4w9WgXcQ';
const OUT_DIR = new URL('./out/', import.meta.url);
const TV_USER_AGENT =
  'Mozilla/5.0 (Web0S; Linux/SmartTV) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.5359.211 Safari/537.36 WebAppManager';
const PLAYING = 1;

mkdirSync(OUT_DIR, { recursive: true });

const browser = await chromium.launch({ channel: 'chromium' });
const context = await browser.newContext({
  userAgent: TV_USER_AGENT,
  viewport: { width: 1920, height: 1080 }
});
const userScript = readFileSync(USER_SCRIPT, 'utf8');
await context.addInitScript({
  content:
    '(() => {\n' +
    'if (window.top !== window || location.protocol === "about:") return;\n' +
    'const run = () => {\n' +
    userScript +
    '\n};\n' +
    'if (document.readyState === "loading") {\n' +
    '  document.addEventListener("DOMContentLoaded", run, { once: true });\n' +
    '} else {\n' +
    '  run();\n' +
    '}\n' +
    '})();'
});
const page = await context.newPage();

const hookWarnings = [];
page.on('console', (message) => {
  if (message.text().includes('[persian-subtitles]')) {
    hookWarnings.push(message.text());
  }
});

const shot = (name) =>
  page.screenshot({ path: new URL(name, OUT_DIR).pathname });

const focusedLabel = () =>
  page.evaluate(() => {
    const element = document.activeElement;
    if (!element) return '';
    return (
      element.getAttribute('aria-label') ||
      element.textContent ||
      ''
    ).trim();
  });

async function focus(label, key) {
  for (let presses = 0; presses < 30; presses++) {
    if ((await focusedLabel()).startsWith(label)) return;
    await page.keyboard.press(key);
    await page.waitForTimeout(400);
  }
  throw new Error(
    `Could not focus "${label}" with ${key}; focused "${await focusedLabel()}"`
  );
}

async function open(label, key) {
  await focus(label, key);
  await page.keyboard.press('Enter');
  await page.waitForTimeout(1500);
}

const playerState = () =>
  page.evaluate(() =>
    document.querySelector('.html5-video-player')?.getPlayerState?.()
  );

const activeTrack = () =>
  page.evaluate(() =>
    document
      .querySelector('.html5-video-player')
      ?.getOption?.('captions', 'track')
  );

try {
  await page.goto(`https://www.youtube.com/tv#/watch?v=${VIDEO_ID}`);
  await page.waitForFunction(
    () =>
      document.activeElement?.textContent?.includes('Watch as guest') ||
      document.activeElement?.textContent?.includes('Add account') ||
      document.querySelector('.html5-video-player')?.getPlayerState?.() === 1,
    null,
    { timeout: 60000 }
  );
  if ((await playerState()) !== PLAYING) {
    await open('Watch as guest', 'ArrowDown');
  }
  await page.waitForFunction(
    () =>
      document.querySelector('.html5-video-player')?.getPlayerState?.() === 1,
    null,
    { timeout: 60000 }
  );
  await page
    .getByText("You're signed out")
    .waitFor({ state: 'hidden', timeout: 30000 });

  await page.keyboard.press('ArrowDown');
  await page.waitForTimeout(1000);
  await open('Settings', 'ArrowRight');
  await open('Captions', 'ArrowDown');
  await open('Auto-translated', 'ArrowDown');
  await shot('menu.png');

  const firstRow = await focusedLabel();
  if (firstRow !== 'Persian') {
    throw new Error(
      `First Auto-translate row is "${firstRow}", expected "Persian"`
    );
  }
  const persianRows = await page.evaluate(
    () =>
      [...document.querySelectorAll('ytlr-button')].filter(
        (button) => button.textContent.trim() === 'Persian'
      ).length
  );
  if (persianRows !== 1) {
    throw new Error(`Found ${persianRows} Persian rows, expected 1`);
  }

  await page.keyboard.press('Enter');
  await page.waitForFunction(
    () =>
      document
        .querySelector('.html5-video-player')
        ?.getOption?.('captions', 'track')?.translationLanguage
        ?.languageCode === 'fa',
    null,
    { timeout: 15000 }
  );
  await page.waitForTimeout(1500);
  await shot('captions-menu.png');
  for (let presses = 0; presses < 3; presses++) {
    await page.keyboard.press('Escape');
    await page.waitForTimeout(800);
  }
  await page.waitForFunction(
    () =>
      [...document.querySelectorAll('[class*=caption]')].some((element) =>
        /[؀-ۿ]/.test(element.textContent ?? '')
      ),
    null,
    { timeout: 30000 }
  );
  await page.waitForTimeout(1500);
  await shot('captions.png');

  const track = await activeTrack();
  if (track?.languageCode !== 'en') {
    throw new Error(
      `Persian is translated from "${track?.languageCode}", expected "en"`
    );
  }
  if (hookWarnings.length > 0) {
    throw new Error(`Hook warnings: ${hookWarnings.join(' | ')}`);
  }

  console.log(`PASS: ${track.displayName}`);
} catch (error) {
  await shot('failure.png');
  console.error(`FAIL: ${error.message}`);
  if (hookWarnings.length > 0) {
    console.error(`Hook warnings: ${hookWarnings.join(' | ')}`);
  }
  process.exitCode = 1;
} finally {
  await browser.close();
}
