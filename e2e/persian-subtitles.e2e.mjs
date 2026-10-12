import { resolve } from 'node:path';
import {
  activeTrack,
  captionText,
  closeMenus,
  focusedLabel,
  launchTv,
  openAutoTranslate,
  playVideo,
  selectFocusedPersian,
  shot
} from './tv.mjs';

const USER_SCRIPT = resolve(
  process.argv[2] ?? '../youtube-webos/dist/webOSUserScripts/userScript.js'
);
const VIDEO_ID = process.argv[3] ?? 'dQw4w9WgXcQ';

const { browser, page } = await launchTv(USER_SCRIPT);

const hookWarnings = [];
page.on('console', (message) => {
  if (message.text().includes('[persian-subtitles]')) {
    hookWarnings.push(message.text());
  }
});

try {
  await playVideo(page, VIDEO_ID);
  await openAutoTranslate(page);
  await shot(page, 'menu.png');

  const firstRow = await focusedLabel(page);
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

  await selectFocusedPersian(page);
  await page.waitForTimeout(1500);
  await shot(page, 'captions-menu.png');
  await closeMenus(page);
  await page.waitForFunction(
    () =>
      [...document.querySelectorAll('[class*=caption]')].some((element) =>
        /[؀-ۿ]/.test(element.textContent ?? '')
      ),
    null,
    { timeout: 30000 }
  );
  await page.waitForTimeout(1500);
  await shot(page, 'captions.png');
  console.log('caption:', await captionText(page));

  const track = await activeTrack(page);
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
  await shot(page, 'failure.png');
  console.error(`FAIL: ${error.message}`);
  if (hookWarnings.length > 0) {
    console.error(`Hook warnings: ${hookWarnings.join(' | ')}`);
  }
  process.exitCode = 1;
} finally {
  await browser.close();
}
