# YouTube AdFree with AI Persian subtitles

A personal build of [webosbrew/youtube-webos](https://github.com/webosbrew/youtube-webos) plus a small home server.
Pick **Persian** under **Settings → Captions → Auto-translated**, and the TV shows Persian subtitles translated by a local AI model on the PC, or on the ThinkPad when the PC is off.
If neither machine answers, the TV shows YouTube's own Persian translation.

- Designs: `docs/superpowers/specs/2026-10-12-persian-auto-translate-subtitles-design.md`, `docs/superpowers/specs/2026-10-12-ai-persian-subtitles-design.md`
- Plans: `docs/superpowers/plans/2026-10-12-persian-auto-translate-subtitles.md`, `docs/superpowers/plans/2026-10-12-ai-persian-subtitles.md`
- TV app source: `youtube-webos/`, a git submodule pointing to [Ali-Flt/youtube-webos](https://github.com/Ali-Flt/youtube-webos), which is upstream plus the Persian changes.
  Clone with `git clone --recurse-submodules https://github.com/Ali-Flt/yt_auto_sub.git`.
- Server: `server/`

## How it works

When a video starts, the TV app sends the video's English captions to the PC (`192.168.10.139`), or to the ThinkPad (`192.168.10.245`) if the PC does not answer within 3 seconds.
That machine translates them sentence by sentence with a local model, starting at the point you are watching.
When you pick Persian, the TV loads the translated subtitles from that machine and refreshes them every 10 seconds until the whole video is done.

## 1. Install the server

Each machine runs the same Docker setup from the `server/` folder.
The folder is already at `~/persian-subs` on the PC.

### PC on Linux (NVIDIA GPU)

1. Install Docker and the NVIDIA Container Toolkit, then log out and back in:

   ```bash
   sudo pacman -S docker docker-compose nvidia-container-toolkit
   sudo nvidia-ctk runtime configure --runtime=docker
   sudo systemctl enable --now docker
   sudo usermod -aG docker "$USER"
   ```

2. If you already downloaded `translategemma-12b-it-Q4_K_M.gguf`, move it to `~/persian-subs/models/` (create the folder first).
   Otherwise the first start downloads it (7.3 GB).
3. Start the server:

   ```bash
   cd ~/persian-subs
   mkdir -p models cache
   docker compose --env-file pc.env -f docker-compose.yml -f gpu.yaml up -d --build
   ```

   `docker compose --env-file pc.env logs -f model llm` shows the download and the model loading.
   If the image pull keeps failing on a flaky connection, run `./pull-image.sh ghcr.io/ggml-org/llama.cpp:server-cuda12-b11561` first (needs `aria2`).
   It resumes where it stopped, so run it again after any interruption.
4. Check it: `python3 smoke.py` prints `translated 2 sentences` and two Persian lines.
5. If `docker compose --env-file pc.env logs llm` says `failed to initialize CUDA: unknown error`, Docker's list of NVIDIA devices is out of date (this happens after kernel or driver updates).
   Regenerate it and restart the model server:

   ```bash
   sudo nvidia-ctk cdi generate --output=/etc/cdi/nvidia.yaml
   docker compose --env-file pc.env -f docker-compose.yml -f gpu.yaml up -d --force-recreate llm
   ```

### ThinkPad (CPU)

The ThinkPad uses the PC's llama.cpp image; without an NVIDIA GPU it runs the model on the processor.
Everything except the model is copied from the PC over the LAN, so nothing else is downloaded.

1. Install Docker, then log out and back in:

   ```bash
   sudo pacman -S docker docker-compose
   sudo systemctl enable --now docker
   sudo usermod -aG docker "$USER"
   ```

2. On the PC, copy the server folder and the Docker images to the ThinkPad:

   ```bash
   rsync -a --exclude cache --exclude models --exclude setup.log ~/persian-subs ali@192.168.10.245:
   docker save ghcr.io/ggml-org/llama.cpp:server-cuda12-b11561 curlimages/curl:8.17.0 persian-subs-subs \
     | zstd -T0 | ssh ali@192.168.10.245 'zstd -d | docker load'
   ```

3. If you downloaded `Hy-MT2-1.8B-Q4_K_M.gguf` yourself, move it to `~/persian-subs/models/` on the ThinkPad.
   Otherwise the first start downloads it (1.1 GB).
4. On the ThinkPad, start the server and check it:

   ```bash
   cd ~/persian-subs
   mkdir -p models cache
   docker compose --env-file thinkpad.env up -d
   python3 smoke.py
   ```

   Leave out `--build`: the server image comes from the PC.

### PC on Windows

1. Install [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) with the WSL 2 backend, and a current NVIDIA driver.
   In Docker Desktop settings, turn on "Start Docker Desktop when you sign in", so the server comes back after a reboot.
2. While booted into Linux, copy the whole folder, including the downloaded model, to an NTFS drive that Windows also uses:

   ```bash
   cp -r ~/persian-subs /run/media/ali/LocalDisk/
   ```

   Linux keeps its own copy in `~/persian-subs`, because the NTFS drives are only mounted after you log in.
3. Boot into Windows and open PowerShell in the `persian-subs` folder on the drive File Explorer labels "LocalDisk".
4. Start the server:

   ```powershell
   docker compose --env-file pc.env -f docker-compose.yml -f gpu.yaml up -d --build
   ```

5. Allow the TV to connect, in an administrator PowerShell:

   ```powershell
   New-NetFirewallRule -DisplayName "persian-subs" -Direction Inbound -Protocol TCP -LocalPort 8765 -Action Allow
   ```

6. Check it from the ThinkPad: `python3 ~/persian-subs/smoke.py http://192.168.10.139:8765`.

### Day to day

- Logs: `docker compose --env-file pc.env logs -f subs` (use `thinkpad.env` on the ThinkPad).
- Stop: `docker compose --env-file pc.env down`.
- Change the model: edit `MODEL_URL`, `MODEL_FILE` and `PROMPT_STYLE` (`hy-mt` or `translategemma`) in the env file, then run the start command again.
  Translations cached by the previous model are ignored and redone with the new one.
- Translations are cached in `cache/`, so a rewatched video is instant.

## 2. Install the TV app

The TV must be in Developer Mode with an active session.

1. The package is on the PC at `~/youtube.leanback.v4_0.5.3_all.ipk`.
2. Install it from the PC: `ares-install -d tv ~/youtube.leanback.v4_0.5.3_all.ipk`, or use webOS Dev Manager (Apps → Install).
   The app ID is unchanged, so this replaces the existing YouTube AdFree.

The server addresses are built into the package.
If an address changes, rebuild the package (see below).

## Use it

Play a video, open **Settings → Captions → Auto-translated**, and pick **Persian**.
Subtitles start where you are watching; lines that are not translated yet appear within about 10 seconds of being ready.

## Check on the TV

- [ ] A video with uploaded English captions shows AI Persian subtitles: full sentences, at most two lines.
- [ ] A video with only auto-generated captions does the same.
- [ ] When the next video starts with Persian still selected, AI subtitles appear within about 10 seconds.
- [ ] With the PC off, subtitles still come (from the ThinkPad).
- [ ] With both machines off, Persian shows YouTube's own translation.
- [ ] A long video keeps getting new lines while you watch.
- [ ] Letters پ چ ژ گ ک ی, half-spaces and punctuation render correctly.
- [ ] Other captions, ad blocking, SponsorBlock and the green-button settings still work.

If something fails, run `ares-inspect -d tv --app youtube.leanback.v4 --open` and look for `[persian-ai]` in the console, and check `docker compose logs subs` on the server.

## Rebuild the TV app

Updating the app from Homebrew Channel or another upstream build removes these changes.
To merge upstream changes and rebuild on the laptop, first add the upstream remote once with `git -C youtube-webos remote add upstream https://github.com/webosbrew/youtube-webos.git`, then:

```bash
cd youtube-webos
git pull --no-rebase upstream main
pnpm install
pnpm run lint:all && pnpm run test:unit
PERSIAN_SUBS_SERVERS="http://192.0.2.1:8765,http://$(hostname -I | awk '{print $1}'):8765" pnpm run build
cd ../e2e && npm install && npx playwright install chromium
node persian-subtitles.e2e.mjs && node ai-subtitles.e2e.mjs
cd ../youtube-webos
PERSIAN_SUBS_SERVERS="http://192.168.10.139:8765,http://192.168.10.245:8765" pnpm run build
pnpm run test:compat && pnpm run package
git push origin main
cd .. && git add youtube-webos && git commit -m "chore: update youtube-webos" && git push
```

The E2E build points at an unreachable address first and this laptop second, so the test covers failover.
Server tests: `cd server && uv run --python 3.13 pytest`.
