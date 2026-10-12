# Persian auto-translated subtitles for YouTube AdFree (webOS)

**Date:** 2026-10-12
**Status:** Draft for review

## Goal

Make **Persian** selectable under **Settings → Captions → Auto-translated** in the webosbrew `youtube-webos` app ("YouTube AdFree") on the user's LG TV.
Foreign-language videos (mostly English) can then show machine-translated Persian captions.

## Background (verified 2026-10-12)

- YouTube can translate any translatable caption track, including auto-generated ones, to Persian (`fa`) via the `tlang` parameter.
  Translation happens server-side (Google Translate).
- The TV client's Auto-translate popup shows only a short list of languages.
  Persian is not in it on the user's TV.
- Selecting other auto-translated languages on the user's TV displays captions correctly, so youtube-webos issue #306 does not affect this TV.
- TizenTube (the Tizen sibling project) solves the same problem in `mods/features/moreSubtitles.js` by patching the TV app's `resolveCommand` when the Auto-translate popup opens.
- `youtube-webos` already has `ResolveCommandRegistry` (`src/app_api/index.ts`), ported from TizenTube, which dispatches hooks by top-level command key.
  Nothing hooks `openPopupAction` today.
- When a translation row is selected, the TV player builds the caption URL itself, including the PO token YouTube requires since 2025.
  We never construct caption URLs.

## Non-goals

- Languages other than Persian, a language picker, or a settings toggle.
- Auto-selecting Persian on every video.
- Our own translation pipeline (LLM or external API).
  Revisit only if YouTube's translation stops working on the TV.
- Transcribing Persian-language speech.
- Upstreaming to webosbrew.
  That is a separate, later decision.

## User experience

1. The user plays a video and opens **Settings → Captions → Auto-translated**.
2. **Persian** is the first entry in the language list.
3. Selecting it shows Persian captions, exactly like any other auto-translated language.
4. Everything else in the app behaves as before.

## Design

### Components

| File | Purpose |
|---|---|
| `src/persian-subtitle-row.ts` | Pure function `withPersianRow(payload)`. No DOM, no globals, unit-testable in Node. |
| `src/persian-subtitles.ts` | Registers an `openPopupAction` hook on `ResolveCommandRegistry` that passes `withPersianRow(payload)` to the original `resolveCommand`. |
| `src/userScript.ts` | One added import of `./persian-subtitles`. |
| Unit test file | `node --test` assertions for `withPersianRow`. Placement must keep the repo's lint, typecheck and `es-check` green. |

### `withPersianRow(payload)`

- **Detection by content, not popup ID.**
  Search the popup recursively for the first array that contains a "translation row": an item whose `compactLinkRenderer` command list includes `selectSubtitlesTrackCommand.translationLanguage`.
  The popup ID has already been renamed across YouTube TV builds (`CLIENT_OVERLAY_TYPE_CAPTIONS_AUTO_TRANSLATE` → `CLIENT_OVERLAY_TYPE_CAPTIONS_LANGUAGE`), so it is not used.
  The caption *track* popup also uses `selectSubtitlesTrackCommand`, but without `translationLanguage`, so it is not matched.
- **Dedupe.**
  If any translation row already has `languageCode === 'fa'`, return the payload unchanged.
- **Row creation by cloning.**
  `structuredClone` the first translation row, then:
  - set `translationLanguage` to `{ languageCode: 'fa', languageName: 'Persian' }`;
  - set the title to `{ simpleText: 'Persian' }`;
  - set the radio icon, if present, to `RADIO_BUTTON_UNCHECKED`;
  - drop fields tied to the source language (`accessibility`, `trackingParams`).
  Cloning inherits whatever follow-up commands (overlay refresh, popup back) the current YouTube build uses, instead of hard-coding them as TizenTube does.
- **Position.**
  Insert immediately before the first translation row.
  This puts Persian at the top of the list without matching English section headers such as "Recommended languages", which would break under a non-English UI.
- **Immutability.**
  Return a new payload with the modified list.
  The input payload is not mutated.
  If nothing matches, return the original payload object.

### Failure behaviour

- The hook wraps `withPersianRow` in `try/catch`.
  On any error it logs one `console.warn` tagged `[persian-subtitles]` and passes the original payload through.
- If YouTube changes the menu structure, the worst case is that Persian silently disappears from the menu.
  The menu itself never breaks.

## Project layout

- `yt_auto_sub/`: this repo, docs only.
- `yt_auto_sub/youtube-webos/`: clone of upstream `webosbrew/youtube-webos`, branch `persian-subtitles`, ignored by this repo's git.

## Build and delivery

The laptop has no network access to the TV.
All TV interaction is done manually by the user on their own LAN.

1. **Laptop (Claude):** `pnpm i`, production build, `ares-package` → `youtube.leanback.v4_<version>_all.ipk`.
2. **User:** copy the `.ipk` to a machine on the TV's LAN (e.g. `scp`).
3. **User:** install it with webOS Dev Manager or `ares-install`, the same way the current AdFree app was installed.
   The app ID is unchanged, so it replaces the existing install.
4. Developer Mode must be active (session not expired) at install time, as for any dev-mode app.

**Caveat:** updating the app later from Homebrew Channel or another upstream build overwrites this build.

## Testing

1. **Unit (laptop):** `node --test` cases for `withPersianRow`:
   - adds exactly one Persian row, before the first translation row, with code `fa`, title "Persian" and an unchecked radio icon;
   - returns the payload unchanged when Persian is already present;
   - returns the payload unchanged for a caption-track popup and for an unrelated popup;
   - does not mutate its input.
2. **Repo checks (laptop):** the repo's lint, typecheck and `test:compat` (`es-check` on `dist/`) pass.
3. **Desktop E2E (laptop, Claude):** Chrome with a webOS TV user agent loads `youtube.com/tv`, with the built `userScript.js` injected at document start.
   Play an English video with captions, open Settings → Captions → Auto-translated, verify the Persian row, select it, verify Persian text in the caption window.
   Screenshot the captions to check glyphs and right-to-left punctuation.
   If YouTube refuses to serve the TV UI to a desktop browser, record that and rely on the TV acceptance test.
4. **TV acceptance (user, on the TV):**
   - [ ] Settings → Captions → Auto-translated lists Persian first.
   - [ ] Selecting Persian shows Persian captions within about 10 seconds.
   - [ ] Persian-specific letters پ چ ژ گ ک ی render (no boxes).
   - [ ] Sentence-final punctuation sits on the left (correct RTL).
   - [ ] Other auto-translated languages and normal captions still work.
   - [ ] Ad blocking, SponsorBlock and the green-button settings still work.
   - [ ] Note whether Persian stays selected on the next video (informational only).
   - If anything fails, capture console output with `ares-inspect --app youtube.leanback.v4 --open` from the LAN machine and look for `[persian-subtitles]`.

Font or text-direction CSS fixes (e.g. extending `src/font-fix.css`) are added only if checks 3 or 4 show a real rendering problem.

## Risks

- **YouTube TV UI changes:** handled by content-based detection, row cloning and pass-through on mismatch.
- **Rate limiting (HTTP 429) on translated captions:** YouTube-side and occasional.
  Same behaviour as any other auto-translated language, so not mitigated here.
- **Radio state cosmetics:** if Persian is active and YouTube does not list it itself, our row shows as unchecked.
  Accepted.
- **Upstream rewrite (webosbrew #475, Cobalt port):** the change may need porting later.
  It is about 60 lines.
