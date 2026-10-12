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
   scp <laptop>:/home/ali/Documents/ali/yt_auto_sub/youtube-webos/youtube.leanback.v4_0.5.3_all.ipk .
   ```

2. Install it the same way you installed YouTube AdFree:
   - **webOS Dev Manager:** Apps → Install → choose `youtube.leanback.v4_0.5.3_all.ipk`.
   - **CLI:** `ares-install -d <tv-device-name> youtube.leanback.v4_0.5.3_all.ipk`

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
