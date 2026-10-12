import { mkdirSync, readFileSync } from 'node:fs';
import { chromium } from 'playwright';

export const OUT_DIR = new URL('./out/', import.meta.url);
const TV_USER_AGENT =
  'Mozilla/5.0 (Web0S; Linux/SmartTV) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/108.0.5359.211 Safari/537.36 WebAppManager';
// webOS's WebAppManager allows insecure (http) requests from the https YouTube page.
const WEBOS_LIKE_ARGS = [
  '--allow-running-insecure-content',
  '--disable-features=LocalNetworkAccessChecks,PrivateNetworkAccessSendPreflights,BlockInsecurePrivateNetworkRequests'
];
const PLAYING = 1;

mkdirSync(OUT_DIR, { recursive: true });

export async function launchTv(userScriptPath) {
  const browser = await chromium.launch({
    channel: 'chromium',
    args: WEBOS_LIKE_ARGS
  });
  const context = await browser.newContext({
    userAgent: TV_USER_AGENT,
    viewport: { width: 1920, height: 1080 }
  });
  const userScript = readFileSync(userScriptPath, 'utf8');
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
  return { browser, page: await context.newPage() };
}

export const shot = (page, name) =>
  page.screenshot({ path: new URL(name, OUT_DIR).pathname });

export const focusedLabel = (page) =>
  page.evaluate(() => {
    const element = document.activeElement;
    if (!element) return '';
    return (
      element.getAttribute('aria-label') ||
      element.textContent ||
      ''
    ).trim();
  });

async function focus(page, label, key) {
  for (let presses = 0; presses < 30; presses++) {
    if ((await focusedLabel(page)).startsWith(label)) return;
    await page.keyboard.press(key);
    await page.waitForTimeout(400);
  }
  throw new Error(
    `Could not focus "${label}" with ${key}; focused "${await focusedLabel(page)}"`
  );
}

export async function open(page, label, key) {
  await focus(page, label, key);
  await page.keyboard.press('Enter');
  await page.waitForTimeout(1500);
}

const playerState = (page) =>
  page.evaluate(() =>
    document.querySelector('.html5-video-player')?.getPlayerState?.()
  );

export const activeTrack = (page) =>
  page.evaluate(() =>
    document
      .querySelector('.html5-video-player')
      ?.getOption?.('captions', 'track')
  );

export async function playVideo(page, videoId) {
  await page.goto(`https://www.youtube.com/tv#/watch?v=${videoId}`);
  await page.waitForFunction(
    () =>
      document.activeElement?.textContent?.includes('Watch as guest') ||
      document.activeElement?.textContent?.includes('Add account') ||
      document.querySelector('.html5-video-player')?.getPlayerState?.() === 1,
    null,
    { timeout: 60000 }
  );
  if ((await playerState(page)) !== PLAYING) {
    await open(page, 'Watch as guest', 'ArrowDown');
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
}

export async function openAutoTranslate(page) {
  await page.keyboard.press('ArrowDown');
  await page.waitForTimeout(1000);
  await open(page, 'Settings', 'ArrowRight');
  await open(page, 'Captions', 'ArrowDown');
  await open(page, 'Auto-translated', 'ArrowDown');
}

export async function selectFocusedPersian(page) {
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
}

export async function closeMenus(page) {
  for (let presses = 0; presses < 3; presses++) {
    await page.keyboard.press('Escape');
    await page.waitForTimeout(800);
  }
}

export const captionText = (page) =>
  page.evaluate(() =>
    [...document.querySelectorAll('[class*=caption]')]
      .map((element) => element.textContent ?? '')
      .join(' ')
  );
