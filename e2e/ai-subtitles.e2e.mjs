// Desktop E2E for AI Persian subtitles.
// Build the userscript first with:
//   PERSIAN_SUBS_SERVERS="http://192.0.2.1:8765,http://<this machine's LAN IP>:8765" pnpm build
// 192.0.2.1 never answers, so the job must fail over to this machine.
import { spawn } from 'node:child_process';
import { mkdtempSync } from 'node:fs';
import { createServer } from 'node:http';
import { tmpdir } from 'node:os';
import { join, resolve } from 'node:path';
import {
  captionText,
  closeMenus,
  launchTv,
  openAutoTranslate,
  playVideo,
  selectFocusedPersian,
  shot
} from './tv.mjs';

const USER_SCRIPT = resolve(
  process.argv[2] ?? '../youtube-webos/dist/webOSUserScripts/userScript.js'
);
const SERVER_DIR = resolve(process.argv[3] ?? '../server');
const VIDEO_ID = 'dQw4w9WgXcQ';
const MARKER = 'هوش مصنوعی';
const FAKE_LLM_DELAY_MS = 1000;

function startFakeLlm() {
  const server = createServer((req, res) => {
    let body = '';
    req.on('data', (chunk) => (body += chunk));
    req.on('end', () => {
      const prompt = JSON.parse(body).messages[0].content;
      const source = prompt.split('\n').at(-1);
      setTimeout(() => {
        res.setHeader('Content-Type', 'application/json');
        res.end(
          JSON.stringify({
            choices: [{ message: { content: `${MARKER}: ${source}` } }]
          })
        );
      }, FAKE_LLM_DELAY_MS);
    });
  });
  return new Promise((done) =>
    server.listen(0, '127.0.0.1', () => done(server))
  );
}

function startSubsServer(llmPort) {
  const child = spawn('python3', ['-m', 'subs.app'], {
    cwd: SERVER_DIR,
    env: {
      ...process.env,
      LLM_URL: `http://127.0.0.1:${llmPort}`,
      PROMPT_STYLE: 'hy-mt',
      MODEL_NAME: 'fake',
      CACHE_DIR: mkdtempSync(join(tmpdir(), 'subs-cache-')),
      PORT: '8765'
    },
    stdio: ['ignore', 'inherit', 'inherit']
  });
  return child;
}

async function waitForCaption(page, predicate, timeout) {
  const started = Date.now();
  while (Date.now() - started < timeout) {
    const text = await captionText(page);
    if (predicate(text)) return text;
    await page.waitForTimeout(500);
  }
  throw new Error(`caption never matched; last: "${await captionText(page)}"`);
}

async function selectPersian(page) {
  await openAutoTranslate(page);
  await selectFocusedPersian(page);
  await closeMenus(page);
}

const llm = await startFakeLlm();
let subs = startSubsServer(llm.address().port);
let tv = await launchTv(USER_SCRIPT);

try {
  const serverFetches = [];
  tv.page.on('request', (request) => {
    if (request.url().includes(':8765/v1/timedtext')) {
      serverFetches.push(request.url());
    }
  });

  await playVideo(tv.page, VIDEO_ID);
  await selectPersian(tv.page);
  const aiCaption = await waitForCaption(
    tv.page,
    (text) => text.includes(MARKER),
    60000
  );
  await shot(tv.page, 'ai-captions.png');
  console.log('AI caption:', aiCaption);

  await tv.page.waitForTimeout(25000);
  if (serverFetches.length < 2) {
    throw new Error(
      `expected the player to reload AI captions, got ${serverFetches.length} fetches`
    );
  }
  console.log('server caption fetches:', serverFetches.length);

  subs.kill();
  await tv.browser.close();
  tv = await launchTv(USER_SCRIPT);
  await playVideo(tv.page, VIDEO_ID);
  await selectPersian(tv.page);
  const fallback = await waitForCaption(
    tv.page,
    (text) => /[؀-ۿ]/.test(text),
    60000
  );
  if (fallback.includes(MARKER)) {
    throw new Error('servers are down but AI captions were shown');
  }
  await shot(tv.page, 'fallback-captions.png');
  console.log('fallback caption:', fallback);

  console.log('PASS: AI captions, reload, failover and fallback');
} catch (error) {
  await shot(tv.page, 'ai-failure.png');
  console.error(`FAIL: ${error.message}`);
  process.exitCode = 1;
} finally {
  subs.kill();
  llm.close();
  await tv.browser.close();
}
