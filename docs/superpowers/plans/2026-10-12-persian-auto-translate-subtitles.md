# Persian Auto-translated Subtitles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Persian" row to the YouTube TV client's CC → Auto-translate menu inside the webosbrew `youtube-webos` app, and deliver an installable `.ipk`.

**Architecture:** A pure function `withPersianRow(payload)` returns a copy of an `openPopupAction` payload with a Persian row cloned from the first existing translation row; it returns the same object for every other payload.
A thin hook module registers it for `openPopupAction` on the app's existing `ResolveCommandRegistry`.
YouTube's own player does the translation (`tlang=fa`) once the row is selected.

**Tech Stack:** TypeScript 6 (strict), webpack + Babel (ES5 output), `node:test` on Node 26 with native type stripping, Playwright 1.64 (Chromium) for desktop E2E.

**Spec:** `docs/superpowers/specs/2026-10-12-persian-auto-translate-subtitles-design.md`

## Global Constraints

- Persian is `{ languageCode: 'fa', languageName: 'Persian' }`; row title is exactly `Persian`.
- Log tag for the hook's only warning: `[persian-subtitles]`.
- No new dependencies in `youtube-webos` (runtime or dev). Unit tests use `node:test` only.
- `youtube-webos` checks that must stay green: `pnpm run build`, `pnpm run lint:all` (eslint, `tsc -b`, prettier), `pnpm run test:compat` (es-check ES5 on `dist/`).
- Unit test file is plain JS under `youtube-webos/test/` (not in any tsconfig; linted by ESLint). Run with `node --test 'test/**/*.test.js'` (glob form; a bare directory argument fails).
- Code style: Prettier config of `youtube-webos` (single quotes, no trailing commas). No code comments unless necessary. No em dashes anywhere.
- Commit messages: conventional commits, no co-author trailer.
- The laptop has no network path to the TV. All TV steps are manual, performed by the user.
- Tooling on the laptop: Node 26.7, `pnpm` 10 at `~/.local/bin/pnpm`, Playwright Chromium cached in `~/.cache/ms-playwright`.

## Review Focus

- **Persian already listed** (YouTube adds it natively later, or the TV UI language is Persian): no duplicate row. Pinned by the Task 1 test "returns the same payload when Persian is already listed".
- **Non-English TV UI** (section headers are translated): the row is still inserted, because insertion never matches header text. Pinned by the Task 1 test "does not depend on English section headers".
- **Copied row is the currently selected language**: the Persian row shows unchecked and the original stays checked. Pinned by the Task 1 test "shows the Persian row unchecked even when the copied row is selected".
- **Recommended row carries `translationSourceTrackIndices`** (verified 2026-10-12: it pointed at a Japanese track, giving "Japanese >> English"): the Persian row must drop it so the player translates from the default track. Pinned by the Task 1 test "drops the source track hint..." and the Task 3 E2E assertion that the active track is `en` → `fa`.
- **Every other popup in the app** (settings, account picker, toasts, malformed shapes) passes through untouched and never throws. Pinned by the Task 1 tests for the caption-track popup and malformed payloads, and by the Task 3 E2E check that no `[persian-subtitles]` warning is logged during the whole navigation.

## File Structure

| Path | Repo | Responsibility |
|---|---|---|
| `youtube-webos/src/persian-subtitle-row.ts` | fork | Pure transform `withPersianRow`. No DOM, no globals. |
| `youtube-webos/src/persian-subtitles.ts` | fork | Registers the `openPopupAction` hook; catches and logs errors. |
| `youtube-webos/src/userScript.ts` | fork | One added import line. |
| `youtube-webos/test/persian-subtitle-row.test.js` | fork | Unit tests against real captured popups. |
| `youtube-webos/test/fixtures/*.json` | fork | Copies of `fixtures/youtube-tv/*.json` from this repo. |
| `youtube-webos/package.json` | fork | Adds `test:unit` script. |
| `e2e/package.json`, `e2e/persian-subtitles.e2e.mjs` | docs repo | Desktop E2E harness (TV user agent, real key presses). |
| `README.md` | docs repo | Rebuild, copy and install instructions for the user. |

`yt_auto_sub/` is the docs repo (already a git repo, ignores `youtube-webos/`).
`yt_auto_sub/youtube-webos/` is a separate git clone of upstream on branch `persian-subtitles`.

---

### Task 1: Fork workspace and `withPersianRow` with unit tests

**Files:**
- Create: `youtube-webos/src/persian-subtitle-row.ts`
- Create: `youtube-webos/test/persian-subtitle-row.test.js`
- Create: `youtube-webos/test/fixtures/auto-translate-popup.json`, `youtube-webos/test/fixtures/captions-language-popup.json` (copied)
- Modify: `youtube-webos/package.json` (scripts)

**Interfaces:**
- Consumes: nothing.
- Produces: `export function withPersianRow<T>(payload: T): T` from `src/persian-subtitle-row.ts`. Returns the same object when nothing changes, a new object otherwise. Never mutates its input.

- [ ] **Step 1: Clone upstream, branch, install, confirm a green baseline**

```bash
cd /home/ali/Documents/ali/yt_auto_sub
git clone https://github.com/webosbrew/youtube-webos.git
cd youtube-webos
git checkout -b persian-subtitles
git log -1 --format='%h %cs'
pnpm install
pnpm run build && pnpm run lint:all && pnpm run test:compat
```

Expected: install succeeds (husky installs a lint-staged pre-commit hook), webpack compiles (3 size warnings are normal), all lint steps and es-check pass.
Record the upstream commit hash in the Task 1 commit message.

- [ ] **Step 2: Copy the captured fixtures and add the `test:unit` script**

```bash
mkdir -p test/fixtures
cp ../fixtures/youtube-tv/auto-translate-popup.json ../fixtures/youtube-tv/captions-language-popup.json test/fixtures/
```

In `package.json`, add this line directly after the `"test:compat": "es-check",` line:

```json
    "test:unit": "node --test 'test/**/*.test.js'",
```

- [ ] **Step 3: Write the failing tests**

Create `test/persian-subtitle-row.test.js`:

```js
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { withPersianRow } from '../src/persian-subtitle-row.ts';

const PERSIAN = { languageCode: 'fa', languageName: 'Persian' };

const fixture = (name) =>
  JSON.parse(readFileSync(new URL(`./fixtures/${name}`, import.meta.url)));

const itemsOf = (payload) =>
  payload.openPopupAction.popup.overlaySectionRenderer.overlay
    .overlayTwoPanelRenderer.actionPanel.overlayPanelRenderer.content
    .overlayPanelItemListRenderer.items;

const commandsOf = (item) =>
  item.compactLinkRenderer?.serviceEndpoint?.commandExecutorCommand?.commands ??
  [];

const languageOf = (item) =>
  commandsOf(item)[0]?.selectSubtitlesTrackCommand?.translationLanguage;

const titleOf = (item) => item.compactLinkRenderer?.title?.simpleText;

const persianRows = (items) =>
  items.filter((item) => languageOf(item)?.languageCode === 'fa');

test('adds one Persian row before the first translation row', () => {
  const input = fixture('auto-translate-popup.json');
  const before = itemsOf(input);

  const after = itemsOf(withPersianRow(input));

  assert.equal(after.length, before.length + 1);
  assert.equal(persianRows(after).length, 1);
  assert.equal(titleOf(after[1]), 'Persian');
  assert.deepEqual(languageOf(after[1]), PERSIAN);
  assert.equal(
    after[1].compactLinkRenderer.secondaryIcon.iconType,
    'RADIO_BUTTON_UNCHECKED'
  );
  assert.deepEqual(
    commandsOf(after[1]).slice(1),
    commandsOf(before[1]).slice(1)
  );
  assert.equal(titleOf(after[2]), 'English');
});

test('drops the source track hint so Persian translates from the default track', () => {
  const input = fixture('auto-translate-popup.json');
  assert.ok(languageOf(itemsOf(input)[1]).translationSourceTrackIndices);

  const persian = itemsOf(withPersianRow(input))[1];

  assert.equal(languageOf(persian).translationSourceTrackIndices, undefined);
});

test('does not mutate its input', () => {
  const input = fixture('auto-translate-popup.json');
  const snapshot = structuredClone(input);

  withPersianRow(input);

  assert.deepEqual(input, snapshot);
});

test('returns the same payload when Persian is already listed', () => {
  const once = withPersianRow(fixture('auto-translate-popup.json'));

  assert.equal(withPersianRow(once), once);
});

test('leaves the caption track popup untouched', () => {
  const input = fixture('captions-language-popup.json');

  assert.equal(withPersianRow(input), input);
});

test('leaves unrelated and malformed payloads untouched', () => {
  const inputs = [
    {},
    [],
    { openPopupAction: { popup: null } },
    {
      openPopupAction: {
        popup: { items: [null, 1, 'x', { compactLinkRenderer: null }] }
      }
    },
    {
      compactLinkRenderer: {
        serviceEndpoint: { commandExecutorCommand: { commands: 'x' } }
      }
    }
  ];

  for (const input of inputs) {
    assert.equal(withPersianRow(input), input);
  }
});

test('does not depend on English section headers', () => {
  const input = fixture('auto-translate-popup.json');
  for (const item of itemsOf(input)) {
    if (item.overlayMessageRenderer) {
      item.overlayMessageRenderer.subtitle.simpleText = 'زبان‌ها';
    }
  }

  const after = itemsOf(withPersianRow(input));

  assert.equal(titleOf(after[1]), 'Persian');
});

test('shows the Persian row unchecked even when the copied row is selected', () => {
  const input = fixture('auto-translate-popup.json');
  itemsOf(input)[1].compactLinkRenderer.secondaryIcon.iconType =
    'RADIO_BUTTON_CHECKED';

  const after = itemsOf(withPersianRow(input));

  assert.equal(
    after[1].compactLinkRenderer.secondaryIcon.iconType,
    'RADIO_BUTTON_UNCHECKED'
  );
  assert.equal(
    after[2].compactLinkRenderer.secondaryIcon.iconType,
    'RADIO_BUTTON_CHECKED'
  );
});
```

- [ ] **Step 4: Run the tests to verify they fail**

Run: `pnpm run test:unit`
Expected: FAIL with `ERR_MODULE_NOT_FOUND` for `src/persian-subtitle-row.ts`.

- [ ] **Step 5: Write the implementation**

Create `src/persian-subtitle-row.ts`:

```ts
type Json = Record<string, unknown>;

const PERSIAN = { languageCode: 'fa', languageName: 'Persian' } as const;

const isObject = (value: unknown): value is Json =>
  typeof value === 'object' && value !== null;

function commandsOf(item: unknown): unknown[] {
  if (!isObject(item)) return [];
  const link = item.compactLinkRenderer;
  if (!isObject(link)) return [];
  const endpoint = link.serviceEndpoint;
  if (!isObject(endpoint)) return [];
  const executor = endpoint.commandExecutorCommand;
  if (!isObject(executor) || !Array.isArray(executor.commands)) return [];
  return executor.commands;
}

function translationLanguageOf(item: unknown): Json | null {
  for (const command of commandsOf(item)) {
    if (!isObject(command)) continue;
    const select = command.selectSubtitlesTrackCommand;
    if (isObject(select) && isObject(select.translationLanguage)) {
      return select.translationLanguage;
    }
  }
  return null;
}

const isTranslationRow = (item: unknown) =>
  translationLanguageOf(item) !== null;

function persianRowFrom(row: unknown): unknown {
  const clone = structuredClone(row);
  if (!isObject(clone) || !isObject(clone.compactLinkRenderer)) return clone;

  const link = clone.compactLinkRenderer;
  link.title = { simpleText: PERSIAN.languageName };
  delete link.accessibility;
  delete link.trackingParams;
  if (isObject(link.secondaryIcon)) {
    link.secondaryIcon = {
      ...link.secondaryIcon,
      iconType: 'RADIO_BUTTON_UNCHECKED'
    };
  }

  for (const command of commandsOf(clone)) {
    if (!isObject(command)) continue;
    const select = command.selectSubtitlesTrackCommand;
    if (isObject(select)) select.translationLanguage = { ...PERSIAN };
  }
  return clone;
}

function withPersian(list: unknown[]): unknown[] | undefined {
  const hasPersian = list.some(
    (item) => translationLanguageOf(item)?.languageCode === PERSIAN.languageCode
  );
  if (hasPersian) return undefined;

  const index = list.findIndex(isTranslationRow);
  return [
    ...list.slice(0, index),
    persianRowFrom(list[index]),
    ...list.slice(index)
  ];
}

function rebuild(node: unknown): unknown {
  if (Array.isArray(node)) {
    if (node.some(isTranslationRow)) return withPersian(node);
    for (let i = 0; i < node.length; i++) {
      const child = rebuild(node[i]);
      if (child !== undefined) {
        return [...node.slice(0, i), child, ...node.slice(i + 1)];
      }
    }
    return undefined;
  }

  if (!isObject(node)) return undefined;
  for (const [key, value] of Object.entries(node)) {
    const child = rebuild(value);
    if (child !== undefined) return { ...node, [key]: child };
  }
  return undefined;
}

export function withPersianRow<T>(payload: T): T {
  const next = rebuild(payload);
  return next === undefined ? payload : (next as T);
}
```

- [ ] **Step 6: Run the tests to verify they pass**

Run: `pnpm run test:unit`
Expected: `ℹ pass 8` and `ℹ fail 0`.

- [ ] **Step 7: Format and run the repo checks**

```bash
pnpm exec prettier --write src/persian-subtitle-row.ts test/
pnpm run lint:all && pnpm run test:unit
```

Expected: all pass. (`tsc -b` does not see the test file; ESLint lints it; Prettier checks the fixtures.)

- [ ] **Step 8: Commit**

```bash
git add package.json src/persian-subtitle-row.ts test/
git commit -m "feat: add withPersianRow transform for the auto-translate popup

Adds a Persian row, cloned from the first translation row, to the TV
client's CC auto-translate popup payload. Fixtures are real popups
captured from youtube.com/tv on 2026-10-12. Based on upstream <hash>."
```

Replace `<hash>` with the value recorded in Step 1.
The pre-commit hook runs lint-staged; it must pass.

---

### Task 2: Desktop E2E harness, proven red without the hook

**Files:**
- Create: `e2e/package.json`
- Create: `e2e/persian-subtitles.e2e.mjs`
- Modify: `.gitignore` (docs repo)

**Interfaces:**
- Consumes: the built `youtube-webos/dist/webOSUserScripts/userScript.js`.
- Produces: `node e2e/persian-subtitles.e2e.mjs [userScriptPath] [videoId]`, which prints `PASS: <track displayName>` and exits 0, or prints `FAIL: <reason>` and exits 1. Screenshots go to `e2e/out/` (`menu.png`, `captions-menu.png`, `captions.png`, or `failure.png`).

Why the harness looks the way it does (all verified on 2026-10-12):
- `youtube.com/tv` serves the real TV UI to Chromium when the user agent is a webOS one. The page CSP allows the injected script.
- The userscript must run at `DOMContentLoaded`, in the top frame only. Injecting at document start makes `spatial-navigation-polyfill.js` and style-loader throw, which silently skips every module imported after `ui.js`, including ours.
- The CC button toggles captions directly. Languages live under Settings → Captions → Auto-translated.
- While the captions menu is open, the player shows a style preview ("Subtitles/CC look like this"), so menus are closed with Escape before checking caption text.
- Focus is read from `document.activeElement` (`aria-label`, else text), so navigation is by name, not by counting key presses.

- [ ] **Step 1: Create the harness package**

Create `e2e/package.json`:

```json
{
  "name": "persian-subtitles-e2e",
  "private": true,
  "type": "module",
  "devDependencies": {
    "playwright": "1.64.0"
  }
}
```

Append to the docs repo `.gitignore`:

```
e2e/node_modules/
e2e/out/
e2e/package-lock.json
```

Run:

```bash
cd /home/ali/Documents/ali/yt_auto_sub/e2e
npm install
npx playwright install chromium
```

- [ ] **Step 2: Write the E2E script**

Create `e2e/persian-subtitles.e2e.mjs`:

```js
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
```

- [ ] **Step 3: Build the fork without the hook and run the E2E to verify it fails**

```bash
cd /home/ali/Documents/ali/yt_auto_sub/youtube-webos && pnpm run build
cd ../e2e && node persian-subtitles.e2e.mjs
```

Expected: `FAIL: First Auto-translate row is "English", expected "Persian"` and exit code 1.
Open `e2e/out/menu.png` and confirm it shows the Auto-translate popup without Persian.
If it fails earlier (for example "Could not focus"), open `e2e/out/failure.png` and fix the harness before continuing; the red result must come from the menu assertion.

- [ ] **Step 4: Commit (docs repo)**

```bash
cd /home/ali/Documents/ali/yt_auto_sub
git add .gitignore e2e/package.json e2e/persian-subtitles.e2e.mjs
git commit -m "test: add desktop E2E harness for the Persian auto-translate row"
```

---

### Task 3: Register the hook, go green end to end

**Files:**
- Create: `youtube-webos/src/persian-subtitles.ts`
- Modify: `youtube-webos/src/userScript.ts` (after the `import './auto-account-select';` line)

**Interfaces:**
- Consumes: `withPersianRow` (Task 1); `ResolveCommandRegistry.getInstance(): Promise<ResolveCommandRegistry>`, `registry.setHook(command: string, fn: ResolveCommandHook)`, and `type ResolveCommandHook = (originalFn, payload: Record<string, unknown>, extra: unknown) => unknown` from `src/app_api/index.ts`.
- Produces: the `openPopupAction` hook in the built userscript.

- [ ] **Step 1: Write the hook module**

Create `src/persian-subtitles.ts`:

```ts
import {
  ResolveCommandRegistry,
  type ResolveCommandHook
} from './app_api/index';
import { withPersianRow } from './persian-subtitle-row';

const hook: ResolveCommandHook = (resolveCommand, payload, extra) => {
  let next = payload;
  try {
    next = withPersianRow(payload);
  } catch (error) {
    console.warn('[persian-subtitles] Passing popup through unchanged:', error);
  }
  return resolveCommand(next, extra);
};

const registry = await ResolveCommandRegistry.getInstance();
registry.setHook('openPopupAction', hook);
```

- [ ] **Step 2: Import it last in the userscript**

In `src/userScript.ts`, add one line after `import './auto-account-select';`:

```ts
import './persian-subtitles';
```

- [ ] **Step 3: Build and run every repo check**

```bash
cd /home/ali/Documents/ali/yt_auto_sub/youtube-webos
pnpm exec prettier --write src/persian-subtitles.ts
pnpm run build && pnpm run lint:all && pnpm run test:compat && pnpm run test:unit
```

Expected: all pass, 8 unit tests pass.

- [ ] **Step 4: Run the E2E to verify it passes**

```bash
cd ../e2e && node persian-subtitles.e2e.mjs
```

Expected: `PASS: English >> Persian`, exit code 0.
An occasional empty or one-word `pageerror` from YouTube's own code also happens on the unmodified upstream build; it is not a failure signal.

- [ ] **Step 5: Review the screenshots like a user would**

Open each file in `e2e/out/` and check:
- `menu.png`: "Persian" is the first row under "Recommended languages", focused, same row style as "English" below it, no duplicate. (A "You're signed out" toast from guest mode may overlap the panel; that is YouTube's.)
- `captions-menu.png`: the captions list shows "Persian (Auto-translated)" with a check mark.
- `captions.png`: menus are closed and a Persian caption is on screen, right to left, with the ♪ marks on the correct sides.

If any screenshot looks wrong, fix the cause before committing.

- [ ] **Step 6: Commit (fork)**

```bash
cd /home/ali/Documents/ali/yt_auto_sub/youtube-webos
git add src/persian-subtitles.ts src/userScript.ts
git commit -m "feat: add Persian to the CC auto-translate menu

Registers an openPopupAction hook that adds a Persian row to the TV
client's auto-translate popup. YouTube translates the captions (tlang=fa)
once the row is selected. Any unexpected popup shape passes through
unchanged."
```

---

### Task 4: Package the `.ipk` and write the install guide

**Files:**
- Create: `README.md` (docs repo)
- Output: `youtube-webos/youtube.leanback.v4_<version>_all.ipk`

**Interfaces:**
- Consumes: the green build from Task 3.
- Produces: an installable `.ipk` and user-facing instructions.

- [ ] **Step 1: Package**

```bash
cd /home/ali/Documents/ali/yt_auto_sub/youtube-webos
pnpm run build && pnpm run package
ls -la youtube.leanback.v4_*_all.ipk
```

Expected: one `.ipk` file. Note its exact file name for the README.

- [ ] **Step 2: Write `README.md`**

Create `/home/ali/Documents/ali/yt_auto_sub/README.md` with this content, with `<ipk>` replaced by the exact file name from Step 1:

````markdown
# YouTube AdFree with Persian auto-translated subtitles

A personal build of [webosbrew/youtube-webos](https://github.com/webosbrew/youtube-webos) that adds **Persian** to **CC → Auto-translate**.
YouTube translates the captions itself; this build only adds the missing menu entry.

- Design: `docs/superpowers/specs/2026-10-12-persian-auto-translate-subtitles-design.md`
- Plan: `docs/superpowers/plans/2026-10-12-persian-auto-translate-subtitles.md`
- Source: `youtube-webos/` (branch `persian-subtitles`)

## Install on the TV

The TV must be in Developer Mode with an active session.

1. On a computer on the same network as the TV, copy the package from the laptop:

   ```bash
   scp <laptop>:/home/ali/Documents/ali/yt_auto_sub/youtube-webos/<ipk> .
   ```

2. Install it the same way you installed YouTube AdFree:
   - **webOS Dev Manager:** Apps → Install → choose `<ipk>`.
   - **CLI:** `ares-install -d <tv-device-name> <ipk>`

   The app ID is unchanged, so this replaces the existing YouTube AdFree.

## Use it

Play a video, open **Settings → Captions → Auto-translated**, and pick **Persian**.
After that, "Persian (Auto-translated)" also appears directly in the captions list.

## Check on the TV

- [ ] Auto-translated lists Persian first.
- [ ] Selecting Persian shows Persian captions within about 10 seconds.
- [ ] Letters پ چ ژ گ ک ی render (no boxes).
- [ ] Sentence-final punctuation sits on the left.
- [ ] Other auto-translated languages and normal captions still work.
- [ ] Ad blocking, SponsorBlock and the green-button settings still work.
- [ ] Note whether Persian stays selected on the next video.

If something fails, run `ares-inspect --app youtube.leanback.v4 --open` from the computer on the TV's network and look for `[persian-subtitles]` in the console.

## Rebuild

Updating the app from Homebrew Channel or another upstream build removes Persian.
To rebuild on the laptop:

```bash
cd youtube-webos
git fetch origin && git rebase origin/main
pnpm install
pnpm run build && pnpm run lint:all && pnpm run test:compat && pnpm run test:unit
cd ../e2e && node persian-subtitles.e2e.mjs
cd ../youtube-webos && pnpm run package
```

Then install the new `.ipk` as above.
````

- [ ] **Step 3: Commit (docs repo)**

```bash
cd /home/ali/Documents/ali/yt_auto_sub
git add README.md
git commit -m "docs: add install and rebuild guide"
```

- [ ] **Step 4: Hand off to the user**

Report: the `.ipk` path, the `scp` and install commands, the TV checklist, and the three E2E screenshots.
Wait for the user's TV results before claiming the feature works on the TV.
