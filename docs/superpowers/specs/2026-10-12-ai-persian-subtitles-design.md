# AI-translated Persian subtitles for YouTube AdFree (webOS)

**Date:** 2026-10-12
**Status:** Draft for review
**Builds on:** `2026-10-12-persian-auto-translate-subtitles-design.md` (the Persian row under Auto-translated, shipped and confirmed on the TV)

## Goal

When the user picks **Settings → Captions → Auto-translated → Persian** on the TV, show Persian subtitles produced by a local AI model on the user's own machines, instead of YouTube's fragment-by-fragment machine translation.
Subtitles are full sentences, at most two lines, and appear while the rest of the video is still being translated.

## Background (verified 2026-10-12)

- YouTube's Persian on the TV is hard to read because it translates short caption fragments one by one.
  Persian puts the verb last, so fragments translate badly and flash by quickly.
- The TV player loads captions with one XHR to `/api/timedtext` (`fmt=json3`, `c=TVHTML5`, no PO token).
  It sends that XHR with `withCredentials = true` and eight `x-goog-*` / `x-youtube-*` headers.
- Desktop probe (TV harness, Chromium with insecure content allowed like webOS): rewriting that XHR's URL to a LAN server works, and the player renders the server's json3 with its normal caption renderer.
  The server must answer the CORS preflight with the request's exact `Origin`, `Access-Control-Allow-Credentials: true`, the requested headers echoed back, and `Access-Control-Allow-Private-Network: true`.
  With `Access-Control-Allow-Headers: *` the preflight fails (credentialed requests do not accept the wildcard).
- `player.setOption('captions', 'reload', true)` makes the player fetch captions again, so new lines can be added while translation runs.
- The page can read the caption track list from `player.getPlayerResponse().captions.playerCaptionsTracklistRenderer.captionTracks` and fetch `baseUrl + '&fmt=json3'` itself (no token, no 429).
  Uploaded tracks carry sentence punctuation; auto-generated (ASR) tracks carry per-word timing, punctuation on recent videos, and `>>` at speaker changes.
- On the user's TV (LG 85QNED93A6A, webOS 25, Chromium 120, Wi-Fi) the app can XHR a plain-HTTP LAN server.
  Mixed content is only a warning; Chrome first sends an `OPTIONS` preflight.
  Callbacks fire only while the app is in the foreground.
- `yt-dlp` on a server fetches original tracks but gets HTTP 429 on translated tracks, and the PC's internet goes through a slow VPN with a datacenter egress IP.
- Machines: PC (RTX 3070 Ti 8 GB, Linux, also boots Windows, not always on), ThinkPad T440p (CPU only, always on).
- The translation model is being chosen by a blind test (Hy-MT2-7B, TranslateGemma-12B, Hy-MT2-1.8B, Google Translate).
  The model is configuration; nothing in this design depends on which one wins.

## Non-goals

- Transcribing audio ("option 2").
  It gets its own spec if the blind test shows caption translation is not good enough.
- Languages other than Persian, and any settings UI on the TV.
- Videos without English captions (YouTube's own behaviour stays).
- Access from outside the LAN, authentication, or sharing a cache between the two machines.

## User experience

1. The user opens a video.
   The TV quietly sends the video's English captions to the PC, or to the ThinkPad if the PC does not answer.
2. The user picks Settings → Captions → Auto-translated → Persian.
3. AI Persian subtitles appear.
   Translation starts at the current playback position, so resumed videos get subtitles first where the user is watching.
   Lines not yet translated appear within about 10 seconds of being ready.
4. If neither machine answers, or the video has no English captions, the Persian row shows YouTube's own Persian, as it does today.

## Architecture

```
TV: YouTube AdFree (youtube-webos fork)
  video opens  -> read English captions from the player -> POST /v1/jobs
                  PC first (3 s timeout), then ThinkPad; remember the winner for this video
  Persian on   -> player's timedtext XHR is rewritten to <winner>/v1/timedtext
  translating  -> poll <winner>/v1/status every 10 s; reload captions when new lines exist

Each machine: docker compose
  subs  (our server, port 8765) -> llm (llama.cpp llama-server, internal only)
  model (one-shot downloader into MODELS_DIR)
```

### TV side (fork `youtube-webos`, branch `persian-subtitles`)

| File | Purpose |
|---|---|
| `src/persian-ai-core.ts` | Pure functions, unit-tested: pick the English track, build the job payload, rewrite a timedtext URL, decide whether to reload. |
| `src/persian-ai-subtitles.ts` | Wiring: video-change detection, job POST with failover, XHR `open` hook, status poll and caption reload. |
| `src/userScript.ts` | One added import. |
| Build config | `PERSIAN_SUBS_SERVERS`, a comma-separated list of server base URLs in priority order, injected at build time. |

Behaviour:

- **Track choice.**
  Prefer an uploaded English track (`languageCode` starting with `en`, `kind` not `asr`), else the English ASR track.
  No English track: do nothing for this video.
- **Job submit.**
  Fetch the track as json3 and POST `{videoId, title, track: {languageCode, kind}, positionMs, events}` to each server in order, 3 s timeout each.
  The first 2xx response wins and is remembered for this video.
- **XHR rewrite.**
  A `/api/timedtext` request with `tlang=fa` for a video that has a winning server is rewritten to `<server>/v1/timedtext?v=<videoId>&t=<positionMs>`.
  Every other request is untouched, so all other captions and the fallback keep YouTube's behaviour.
- **Progressive reload.**
  While the active track's `translationLanguage.languageCode` is `fa` and the job is not done, poll `/v1/status` every 10 s and call `setOption('captions', 'reload', true)` when the translated count has grown.
  Polling stops when the job is done, the track changes, or the video changes.
- **Failure handling.**
  Every failure is caught, logged once with `console.warn('[persian-ai] …')`, and leaves YouTube's behaviour in place.
  Nothing throws into the app.

### Server (`server/` in this repo)

Python 3.13, standard library only (`http.server.ThreadingHTTPServer`, `threading`, `json`, `urllib`).

**Endpoints** (all JSON):

| Method and path | Result |
|---|---|
| `POST /v1/jobs` | `202 {status, done, total}`. Idempotent per video and source track (hash of the events); a known job only updates its priority position. |
| `GET /v1/timedtext?v=&t=` | json3 `{wireMagic: "pb3", events: [...]}` with every cue translated so far; `t` updates the priority position. Unknown video: 404. |
| `GET /v1/status?v=&t=` | `{status: queued, working, done or failed, done, total}`. |
| `GET /healthz` | `200 {model}`. |
| `OPTIONS *` | `204`. |

Every response carries: `Access-Control-Allow-Origin` = the request's `Origin`, `Access-Control-Allow-Credentials: true`, `Access-Control-Allow-Headers` = the request's `Access-Control-Request-Headers`, `Access-Control-Allow-Methods: GET, POST, OPTIONS`, `Access-Control-Allow-Private-Network: true`, `Vary: Origin`.

**Pipeline** (the blind-test spike's logic, cleaned up):

1. **Sentence units.**
   Uploaded tracks: merge cues until sentence-final punctuation.
   ASR tracks: rebuild words with absolute times, split at sentence punctuation and at `>>` speaker changes.
   Both: a unit is cut at 12 s or 40 words; short consecutive same-speaker units are merged up to 20 words and 7 s; a sound tag like `(music)` is its own unit.
2. **Translation.**
   One unit per request to `llm` (`/v1/chat/completions`), with the three previous English units as context.
   The prompt follows the model's documented format, selected by `PROMPT_STYLE`: `hy-mt` (Hy-MT2 "background information" template) or `translategemma` (its chat template, no context).
   Request timeout 120 s; one retry; after that the unit keeps its English text and the failure is logged.
3. **Normalization.**
   Arabic `ي`/`ك` become Persian `ی`/`ک`; whitespace is collapsed; the zero-width non-joiner is kept.
4. **Cue shaping.**
   At most 2 lines of 42 characters (break at the space nearest the middle, preferring after punctuation).
   A unit longer than 84 characters is split into several cues, with time divided by character count.
   A speaker change starts the cue with `- `.

**Worker.**
One thread.
It works on the job most recently requested by the TV.
Within a job it translates the first untranslated unit at or after the latest requested position, wrapping to the start when it reaches the end.

**Cache.**
One JSON file per video and source in `CACHE_DIR`: units, translations, model name, status.
Written after every unit and loaded at startup, so a restart resumes and a rewatch is instant.

**Configuration** (environment): `LLM_URL`, `PROMPT_STYLE`, `MODEL_NAME`, `PORT` (default 8765), `CACHE_DIR`.

### Packaging (Docker)

`server/docker-compose.yml` with three services:

| Service | Image | Role |
|---|---|---|
| `model` | `curlimages/curl` | One-shot: download `MODEL_URL` to `MODELS_DIR/MODEL_FILE` if missing (`curl -C -`, resumable). |
| `llm` | `${LLM_IMAGE}`: `ghcr.io/ggml-org/llama.cpp:server-cuda12-b11561` (PC) or `:server-b11561` (ThinkPad) | `llama-server` on the model; reachable only from `subs`. Starts after `model` completes. |
| `subs` | built from `server/Dockerfile` (`python:3.13-slim`) | Our server; publishes port 8765. |

- `llm` and `subs` use `restart: unless-stopped`, so they come back after a reboot once Docker is running.
- `gpu.yaml` is a compose override that reserves the NVIDIA GPU for `llm`.
- `pc.env` and `thinkpad.env` hold each machine's `LLM_IMAGE`, `MODEL_URL`, `MODEL_FILE`, `PROMPT_STYLE` and llama.cpp flags.
  Provisional models until the blind test decides: PC Hy-MT2-7B, ThinkPad Hy-MT2-1.8B.
- Start command: PC `docker compose --env-file pc.env -f docker-compose.yml -f gpu.yaml up -d`; ThinkPad `docker compose --env-file thinkpad.env up -d`.
- **Windows:** Docker Desktop (WSL 2 backend, NVIDIA GPU support), same command as the PC.
  `MODELS_DIR` and `CACHE_DIR` may point to a folder on an NTFS drive that Linux also mounts, so the model is downloaded once.
  Windows Firewall must allow inbound TCP 8765.
- **Host requirements:** PC Linux: Docker and NVIDIA Container Toolkit. ThinkPad: Docker. Windows: Docker Desktop.
- **Network requirement:** the PC and the ThinkPad have DHCP reservations, because their addresses are built into the TV app.

## Failure behaviour

| Situation | Result |
|---|---|
| PC off or not answering | TV uses the ThinkPad after 3 s. |
| Both off | No rewrite; YouTube's own Persian. |
| Video has no English captions | Nothing is sent; YouTube's behaviour. |
| Server restarts mid-job | Docker restarts it; the job resumes from the cache; the TV's next poll continues. |
| Model fails on a unit twice | That unit shows English; logged on the server. |
| App in the background | webOS pauses callbacks; work continues on the server. |
| YouTube changes the caption request | The hook does not match; YouTube's own Persian. |

## Testing

1. **Server unit tests** (`pytest`, dev-only): sentence units (trimmed fixtures from the four spike videos, both track kinds), cue shaping, normalization, prompt rendering per style, CORS headers on every response including the credentialed preflight, worker order from a requested position, cache resume, API with a fake LLM.
2. **TV unit tests** (`node:test`): track choice, URL rewrite, server order and failover decision, reload decision.
3. **Desktop E2E** (existing Playwright TV harness; Chromium started with `--allow-running-insecure-content` to match webOS): the `subs` container plus a deterministic fake LLM.
   - Selecting Persian shows AI text.
   - Lines grow during translation via reload.
   - First server unreachable: the second is used.
   - Both unreachable: YouTube's Persian.
4. **PC integration:** the compose stack on the PC with the GPU and the chosen model; record time to translate a 10-minute video.
5. **TV acceptance (user):**
   - [ ] Persian shows AI subtitles on a video with uploaded English captions and on one with only auto-generated captions.
   - [ ] With the PC off, subtitles come from the ThinkPad.
   - [ ] Lines keep appearing while a long video is still being translated.
   - [ ] Persian letters, half-spaces and punctuation render correctly.
   - [ ] Other captions, ad blocking and SponsorBlock still work.

## Rollout

1. PC on Linux, deployed over SSH.
2. ThinkPad: over SSH if it joins Tailscale, otherwise by the user with the README.
3. Build the `.ipk` with both server addresses; the user installs it.
4. Windows: the user follows the README.

## Risks

- **ThinkPad speed.**
  Hy-MT2-1.8B ran at about real time on a faster laptop CPU; the T440p is measured at deploy.
  Long videos may outrun the translation; starting at the playback position limits the impact.
- **webOS updates** that start blocking mixed content would need HTTPS on the LAN.
  Not handled now.
- **Upstream rewrite** (webosbrew #475) may require porting the TV hook.
- **YouTube changes** to the caption request fall back to YouTube's behaviour, never to a broken menu.
