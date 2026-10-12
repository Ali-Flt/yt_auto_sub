# AI-Translated Persian Subtitles Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** When the user picks Persian under Settings → Captions → Auto-translated on the TV, show Persian subtitles translated by a local model on the PC (ThinkPad as fallback), served by a Docker stack, with YouTube's own Persian as the last resort.

**Architecture:** A stdlib-only Python server (`server/`) rebuilds English caption fragments into sentences, translates them one by one through llama.cpp's `llama-server`, and serves YouTube json3 with credentialed-CORS headers.
Docker Compose runs a one-shot model downloader, `llama-server` (CUDA on the PC, CPU on the ThinkPad) and the server.
In the TV app (fork `youtube-webos`), a new module posts the player's English captions to the first server that answers and rewrites the player's `tlang=fa` caption XHR to that server, reloading captions while translation progresses.

**Tech Stack:** Python 3.13 (stdlib; pytest for tests, run with `uv`), Docker Compose, llama.cpp server images, TypeScript in the youtube-webos webpack/Babel ES5 toolchain, `node:test`, Playwright (desktop TV harness).

**Spec:** `docs/superpowers/specs/2026-10-12-ai-persian-subtitles-design.md`

## Global Constraints

- Server runtime uses the Python standard library only; `pytest` is a dev dependency (`uv run --python 3.13 pytest`).
- Server listens on port `8765`; every response carries the credentialed CORS headers from the spec (`Access-Control-Allow-Origin` = request `Origin`, `Access-Control-Allow-Credentials: true`, echoed `Access-Control-Allow-Headers`, `Access-Control-Allow-Private-Network: true`).
- Pinned images: `ghcr.io/ggml-org/llama.cpp:server-cuda12-b11561` (PC), `ghcr.io/ggml-org/llama.cpp:server-b11561` (ThinkPad), `curlimages/curl:8.17.0`, `python:3.13-slim`.
- Provisional models until the blind test decides: PC `Hy-MT2-7B-Q4_K_M.gguf`, ThinkPad `Hy-MT2-1.8B-Q4_K_M.gguf`, both `PROMPT_STYLE=hy-mt`.
- TV code must keep `pnpm run lint:all`, `pnpm run test:unit` and `pnpm run test:compat` (ES5) green; run tools through `pnpm exec`, never `npx`, inside `youtube-webos/`.
- The Persian row from the previous feature stays unchanged.
- Server addresses: PC `http://192.168.10.139:8765`; ThinkPad `http://THINKPAD_IP:8765`, where `THINKPAD_IP` is the address the user gives at plan review (DHCP-reserved).
- Branches: docs repo `ai-subtitles` (from `main`); fork `persian-ai-subtitles` (from `persian-subtitles`).
- Commit messages carry no co-author line.
- Markdown: no em dashes; one sentence per line.
- Pre-validated: every code block in this plan was run in a scratch copy on 2026-10-12 (server 39 tests, compose stack on CPU with Hy-MT2-1.8B, fork lint/unit/compat/build, both desktop E2E harnesses).

## Review Focus

1. **Persian still selected when the next video starts:** the player asks for `tlang=fa` before the job exists, so YouTube's Persian shows first; once the job is accepted the module reloads captions and AI subtitles must replace it within about 10 seconds. The desktop harness cannot reproduce this (a reload loses the guest session), so it is pinned by the TV checklist in Task 7.
2. **Resumed or seeked videos:** translation must start at the viewer's position; pinned by `test_work_starts_at_viewer_position_and_wraps` (Task 2) and the `t` parameter on every TV request (Task 6).
3. **Server restart mid-job:** the job must resume from the cache, not restart; pinned by `test_cache_survives_restart` (Task 2).
4. **Model still loading or unreachable at stack start:** units must wait, not fall back to English; pinned by `test_translate_unit_waits_while_model_is_loading_or_unreachable` (Task 2).
5. **Credentialed caption XHR from the player:** a wildcard `Access-Control-Allow-Headers` breaks it; pinned by `test_credentialed_preflight_from_the_player_is_allowed` (Task 3) and the AI E2E (Task 6).

---

### Task 1: Sentence units, prompts and cue shaping

**Files:**
- Modify: `.gitignore`
- Create: `server/pyproject.toml`
- Create: `server/subs/__init__.py` (empty)
- Create: `server/tests/fixtures/uploaded.json`, `server/tests/fixtures/asr.json`
- Create: `server/tests/test_pipeline.py`
- Create: `server/subs/pipeline.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `subs.pipeline` with `Unit(start: int, end: int, en: str, speaker_change: bool = False)`, `build_units(events: list[dict], asr: bool) -> list[Unit]`, `build_request(style: str, text: str, context: list[str], title: str) -> tuple[str, dict]`, `parse_response(path: str, body: dict) -> str`, `normalize(text: str) -> str`, `wrap(text: str) -> list[str]`, `shape_cues(text: str, start: int, end: int, speaker_change: bool) -> list[dict]`, `PROMPT_STYLES = ('hy-mt', 'translategemma')`.

- [ ] **Step 1: Create the branch and project files**

```bash
cd /home/ali/Documents/ali/yt_auto_sub
git checkout -b ai-subtitles
mkdir -p server/subs server/tests/fixtures
touch server/subs/__init__.py
printf 'server/models/\nserver/cache/\nserver/.venv/\n__pycache__/\n.pytest_cache/\n.lavish/\n' >> .gitignore
```

`server/pyproject.toml`:

```toml
[project]
name = "persian-subs"
version = "0.1.0"
description = "LAN server that translates YouTube captions to Persian with a local model"
requires-python = ">=3.12"
dependencies = []

[dependency-groups]
dev = ["pytest>=8"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

`server/tests/fixtures/uploaded.json` (Veritasium `wt4p2oalmRY`, uploaded English, 2:00 to 2:30):

```json
{
 "events": [
  {
   "tStartMs": 120720,
   "dDurationMs": 1500,
   "segs": [
    {
     "utf8": "we wanted to run a test,"
    }
   ]
  },
  {
   "tStartMs": 122220,
   "dDurationMs": 2750,
   "segs": [
    {
     "utf8": "but it turns out that getting\nthe sample isn't so easy."
    }
   ]
  },
  {
   "tStartMs": 125970,
   "dDurationMs": 1890,
   "segs": [
    {
     "utf8": "All right, we've taken\na garden variety spider"
    }
   ]
  },
  {
   "tStartMs": 127860,
   "dDurationMs": 2220,
   "segs": [
    {
     "utf8": "and knocked it unconscious using CO2."
    }
   ]
  },
  {
   "tStartMs": 130080,
   "dDurationMs": 2730,
   "segs": [
    {
     "utf8": "We brought it over here and\nwe put it down with tape."
    }
   ]
  },
  {
   "tStartMs": 132810,
   "dDurationMs": 3030,
   "segs": [
    {
     "utf8": "I then started pulling out\nthe dragline silk by hand."
    }
   ]
  },
  {
   "tStartMs": 135840,
   "dDurationMs": 1866,
   "segs": [
    {
     "utf8": "It's so light that you can barely feel it."
    }
   ]
  },
  {
   "tStartMs": 137706,
   "dDurationMs": 2544,
   "segs": [
    {
     "utf8": "We've attached it to this\nbig rotating mechanism"
    }
   ]
  },
  {
   "tStartMs": 140250,
   "dDurationMs": 2154,
   "segs": [
    {
     "utf8": "which they custom made to milk spiders."
    }
   ]
  },
  {
   "tStartMs": 142404,
   "dDurationMs": 2583,
   "segs": [
    {
     "utf8": "(bright music)"
    }
   ]
  },
  {
   "tStartMs": 146820,
   "dDurationMs": 2910,
   "segs": [
    {
     "utf8": "No spiders were harmed in\nthe making of this video."
    }
   ]
  },
  {
   "tStartMs": 149730,
   "dDurationMs": 960,
   "segs": [
    {
     "utf8": "Now that we've got our silk,"
    }
   ]
  }
 ]
}
```

`server/tests/fixtures/asr.json` (Ludwig `MBl9q-z7TME`, auto-generated English, 2:00 to 2:15):

```json
{
 "events": [
  {
   "tStartMs": 120000,
   "dDurationMs": 3200,
   "wWinId": 1,
   "segs": [
    {
     "utf8": ">> Oh,",
     "acAsrConf": 0,
     "isSpeakerChange": 1
    },
    {
     "utf8": " and",
     "tOffsetMs": 240,
     "acAsrConf": 0
    },
    {
     "utf8": " no",
     "tOffsetMs": 479,
     "acAsrConf": 0
    },
    {
     "utf8": " head,",
     "tOffsetMs": 719,
     "acAsrConf": 0
    },
    {
     "utf8": " right?",
     "tOffsetMs": 960,
     "acAsrConf": 0
    }
   ]
  },
  {
   "tStartMs": 121190,
   "dDurationMs": 2010,
   "wWinId": 1,
   "aAppend": 1,
   "segs": [
    {
     "utf8": "\n"
    }
   ]
  },
  {
   "tStartMs": 121200,
   "dDurationMs": 2800,
   "wWinId": 1,
   "segs": [
    {
     "utf8": ">> Yeah.",
     "acAsrConf": 0,
     "isSpeakerChange": 1
    },
    {
     "utf8": " Yeah.",
     "tOffsetMs": 239,
     "acAsrConf": 0
    },
    {
     "utf8": " Yeah.",
     "tOffsetMs": 879,
     "acAsrConf": 0
    },
    {
     "utf8": " No",
     "tOffsetMs": 1120,
     "acAsrConf": 0
    },
    {
     "utf8": " head.",
     "tOffsetMs": 1279,
     "acAsrConf": 0
    },
    {
     "utf8": " What",
     "tOffsetMs": 1599,
     "acAsrConf": 0
    },
    {
     "utf8": " did",
     "tOffsetMs": 1680,
     "acAsrConf": 0
    },
    {
     "utf8": " you",
     "tOffsetMs": 1840,
     "acAsrConf": 0
    }
   ]
  },
  {
   "tStartMs": 123190,
   "dDurationMs": 810,
   "wWinId": 1,
   "aAppend": 1,
   "segs": [
    {
     "utf8": "\n"
    }
   ]
  },
  {
   "tStartMs": 123200,
   "dDurationMs": 3120,
   "wWinId": 1,
   "segs": [
    {
     "utf8": "draw?",
     "acAsrConf": 0
    }
   ]
  },
  {
   "tStartMs": 123990,
   "dDurationMs": 2330,
   "wWinId": 1,
   "aAppend": 1,
   "segs": [
    {
     "utf8": "\n"
    }
   ]
  },
  {
   "tStartMs": 124000,
   "dDurationMs": 5360,
   "wWinId": 1,
   "segs": [
    {
     "utf8": ">> I",
     "acAsrConf": 0,
     "isSpeakerChange": 1
    },
    {
     "utf8": " drew",
     "tOffsetMs": 159,
     "acAsrConf": 0
    },
    {
     "utf8": " I",
     "tOffsetMs": 399,
     "acAsrConf": 0
    },
    {
     "utf8": " drew",
     "tOffsetMs": 560,
     "acAsrConf": 0
    },
    {
     "utf8": " a",
     "tOffsetMs": 719,
     "acAsrConf": 0
    },
    {
     "utf8": " delicious",
     "tOffsetMs": 880,
     "acAsrConf": 0
    },
    {
     "utf8": " pie.",
     "tOffsetMs": 1280,
     "acAsrConf": 0
    }
   ]
  },
  {
   "tStartMs": 126310,
   "dDurationMs": 3050,
   "wWinId": 1,
   "aAppend": 1,
   "segs": [
    {
     "utf8": "\n"
    }
   ]
  },
  {
   "tStartMs": 126320,
   "dDurationMs": 4800,
   "wWinId": 1,
   "segs": [
    {
     "utf8": ">> Oh,",
     "acAsrConf": 0,
     "isSpeakerChange": 1
    },
    {
     "utf8": " 3.1415.",
     "tOffsetMs": 240,
     "acAsrConf": 0
    }
   ]
  },
  {
   "tStartMs": 129350,
   "dDurationMs": 1770,
   "wWinId": 1,
   "aAppend": 1,
   "segs": [
    {
     "utf8": "\n"
    }
   ]
  },
  {
   "tStartMs": 129360,
   "dDurationMs": 4879,
   "wWinId": 1,
   "segs": [
    {
     "utf8": ">> I",
     "acAsrConf": 0,
     "isSpeakerChange": 1
    },
    {
     "utf8": " mean,",
     "tOffsetMs": 160,
     "acAsrConf": 0
    },
    {
     "utf8": " maybe.",
     "tOffsetMs": 399,
     "acAsrConf": 0
    },
    {
     "utf8": " Maybe.",
     "tOffsetMs": 1119,
     "acAsrConf": 0
    }
   ]
  },
  {
   "tStartMs": 131110,
   "dDurationMs": 3129,
   "wWinId": 1,
   "aAppend": 1,
   "segs": [
    {
     "utf8": "\n"
    }
   ]
  },
  {
   "tStartMs": 131120,
   "dDurationMs": 4240,
   "wWinId": 1,
   "segs": [
    {
     "utf8": ">> Clever.",
     "acAsrConf": 0,
     "isSpeakerChange": 1
    },
    {
     "utf8": " Oh",
     "tOffsetMs": 1040,
     "acAsrConf": 0
    },
    {
     "utf8": " my",
     "tOffsetMs": 1199,
     "acAsrConf": 0
    },
    {
     "utf8": " god,",
     "tOffsetMs": 1440,
     "acAsrConf": 0
    },
    {
     "utf8": " that",
     "tOffsetMs": 1680,
     "acAsrConf": 0
    },
    {
     "utf8": " was",
     "tOffsetMs": 1839,
     "acAsrConf": 0
    },
    {
     "utf8": " stressful.",
     "tOffsetMs": 2000,
     "acAsrConf": 0
    }
   ]
  },
  {
   "tStartMs": 134229,
   "dDurationMs": 1131,
   "wWinId": 1,
   "aAppend": 1,
   "segs": [
    {
     "utf8": "\n"
    }
   ]
  },
  {
   "tStartMs": 134239,
   "dDurationMs": 2801,
   "wWinId": 1,
   "segs": [
    {
     "utf8": ">> Who",
     "acAsrConf": 0,
     "isSpeakerChange": 1
    },
    {
     "utf8": " is",
     "tOffsetMs": 241,
     "acAsrConf": 0
    },
    {
     "utf8": " this?",
     "tOffsetMs": 401,
     "acAsrConf": 0
    }
   ]
  }
 ]
}
```

- [ ] **Step 2: Write the failing tests**

`server/tests/test_pipeline.py`:

```python
import json
from pathlib import Path

import pytest

from subs.pipeline import (
    build_request,
    build_units,
    normalize,
    parse_response,
    shape_cues,
    wrap,
)

FIXTURES = Path(__file__).parent / 'fixtures'


def events(name):
    return json.loads((FIXTURES / name).read_text(encoding='utf-8'))['events']


def test_uploaded_cues_merge_into_sentences():
    units = build_units(events('uploaded.json'), asr=False)

    first = units[0]
    assert first.en == "we wanted to run a test, but it turns out that getting the sample isn't so easy."
    assert (first.start, first.end) == (120720, 124970)
    assert units[5].en == (
        "We've attached it to this big rotating mechanism which they custom made to milk spiders."
    )


def test_sound_tag_is_its_own_unit():
    units = build_units(events('uploaded.json'), asr=False)

    assert '(bright music)' in [u.en for u in units]


def test_asr_words_split_at_speaker_changes_and_short_lines_merge():
    units = build_units(events('asr.json'), asr=True)

    assert units[0].en == 'Oh, and no head, right?'
    assert units[0].speaker_change
    assert units[1].en == 'Yeah. Yeah. Yeah. No head. What did you draw?'
    assert units[1].speaker_change


def test_unpunctuated_speech_is_cut_at_forty_words():
    words = [{'tStartMs': i * 100, 'dDurationMs': 100, 'segs': [{'utf8': f'w{i}'}]} for i in range(100)]

    units = build_units(words, asr=True)

    assert [len(u.en.split()) for u in units] == [41, 41, 18]


def test_hy_mt_request_carries_context_and_title():
    path, body = build_request('hy-mt', 'It helps.', ['- I wore his clothes.'], 'Hot Ones')

    prompt = body['messages'][0]['content']
    assert path == '/v1/chat/completions'
    assert 'YouTube video "Hot Ones"' in prompt
    assert '- I wore his clothes.' in prompt
    assert prompt.endswith('[Source Text]\nIt helps.')


def test_hy_mt_request_without_context_uses_plain_template():
    _, body = build_request('hy-mt', 'It helps.', [], 'Hot Ones')

    assert body['messages'][0]['content'].endswith(':\n\nIt helps.')


def test_translategemma_request_uses_raw_template():
    path, body = build_request('translategemma', 'It helps.', ['ignored'], 'Hot Ones')

    assert path == '/completion'
    assert body['prompt'].endswith('\n\n\nIt helps.<end_of_turn>\n<start_of_turn>model\n')
    assert 'ignored' not in body['prompt']


def test_unknown_prompt_style_is_rejected():
    with pytest.raises(ValueError, match='unknown prompt style'):
        build_request('gpt', 'x', [], '')


def test_parse_response_reads_both_endpoints():
    assert parse_response('/completion', {'content': 'الف'}) == 'الف'
    assert parse_response('/v1/chat/completions', {'choices': [{'message': {'content': 'ب'}}]}) == 'ب'


def test_normalize_uses_persian_letters_and_keeps_half_space():
    assert normalize('  كتاب   علي‌ها \n') == 'کتاب علی‌ها'


def test_wrap_keeps_short_text_on_one_line():
    assert wrap('سلام دنیا') == ['سلام دنیا']


def test_wrap_balances_two_lines_and_prefers_punctuation():
    text = 'ما یک عنکبوت معمولی را برداشتیم، و با دی‌اکسید کربن بیهوشش کردیم.'

    lines = wrap(text)

    assert lines == ['ما یک عنکبوت معمولی را برداشتیم،', 'و با دی‌اکسید کربن بیهوشش کردیم.']


def test_shape_cues_splits_long_text_and_divides_time():
    text = ' '.join(['کلمه'] * 40)

    cues = shape_cues(text, 1000, 9000, speaker_change=False)

    assert len(cues) == 3
    assert cues[0]['tStartMs'] == 1000
    assert sum(c['dDurationMs'] for c in cues) == 8000
    assert all(len(c['segs'][0]['utf8'].split('\n')) <= 2 for c in cues)


def test_shape_cues_marks_speaker_change():
    cues = shape_cues('آره.', 0, 1000, speaker_change=True)

    assert cues == [{'tStartMs': 0, 'dDurationMs': 1000, 'segs': [{'utf8': '- آره.'}]}]
```

- [ ] **Step 3: Run the tests to see them fail**

Run: `cd server && uv run --python 3.13 pytest tests/test_pipeline.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'subs.pipeline'`.

- [ ] **Step 4: Implement**

`server/subs/pipeline.py`:

```python
"""English caption events -> sentence units -> model prompts -> Persian subtitle cues."""

import math
import re
from dataclasses import dataclass

MAX_UNIT_MS = 12_000
MAX_UNIT_WORDS = 40
SHORT_UNIT_WORDS = 8
MERGE_MAX_WORDS = 20
MERGE_MAX_MS = 7_000
LINE_CHARS = 42
CUE_CHARS = 2 * LINE_CHARS

SENTENCE_END = re.compile(r'[.?!…]["\')\]]*$')
SOUND_TAG = re.compile(r'[(\[][^)\]]*[)\]]')
BREAK_AFTER = re.compile(r'[،,.؛;؟?!:…]$')

HY_MT_PLAIN = (
    'Translate the following text into Persian. Note that you should only output '
    'the translated result without any additional explanation:\n\n{text}'
)
HY_MT_CONTEXT = (
    '[Background Information]\n{background}\n\n'
    'Please translate the following text into Persian, taking the provided background '
    'information into consideration.\n\n[Source Text]\n{text}'
)
TRANSLATEGEMMA = (
    '<start_of_turn>user\nYou are a professional English (en) to Persian (fa) translator. '
    'Your goal is to accurately convey the meaning and nuances of the original English text '
    'while adhering to Persian grammar, vocabulary, and cultural sensitivities.\n'
    'Produce only the Persian translation, without any additional explanations or commentary. '
    'Please translate the following English text into Persian:\n\n\n{text}<end_of_turn>\n'
    '<start_of_turn>model\n'
)
PROMPT_STYLES = ('hy-mt', 'translategemma')


@dataclass
class Unit:
    start: int
    end: int
    en: str
    speaker_change: bool = False


def _speaker_marker(text):
    for marker in ('>>', '- '):
        if text.startswith(marker):
            return True, text[len(marker):].strip()
    return False, text


def _cue_pieces(events):
    for event in events:
        text = ' '.join(''.join(s.get('utf8', '') for s in event.get('segs', [])).split())
        change, text = _speaker_marker(text)
        if text:
            start = event['tStartMs']
            yield start, start + event.get('dDurationMs', 0), text, change


def _word_pieces(events):
    words = []
    for event in events:
        end = event['tStartMs'] + event.get('dDurationMs', 0)
        for seg in event.get('segs', []):
            word = seg.get('utf8', '').strip()
            if word:
                words.append([event['tStartMs'] + seg.get('tOffsetMs', 0), end, word])
    for word, following in zip(words, words[1:]):
        if following[0] > word[0]:
            word[1] = min(word[1], following[0])
    change = False
    for start, end, word in words:
        if word.startswith('>>'):
            change, word = True, word[2:].strip()
            if not word:
                continue
        yield start, end, word, change
        change = False


def build_units(events, asr):
    """Merge caption fragments (uploaded cues or ASR words) into sentence units."""
    units, current = [], None
    for start, end, text, change in (_word_pieces(events) if asr else _cue_pieces(events)):
        sound = SOUND_TAG.fullmatch(text)
        if current and (change or sound):
            units.append(current)
            current = None
        if current is None:
            current = Unit(start, end, text, change)
        else:
            current.end = end
            current.en = f'{current.en} {text}'
        too_long = current.end - current.start > MAX_UNIT_MS or len(current.en.split()) > MAX_UNIT_WORDS
        if sound or SENTENCE_END.search(text) or too_long:
            units.append(current)
            current = None
    if current:
        units.append(current)
    return _merge_short(units)


def _merge_short(units):
    merged = []
    for unit in units:
        prev = merged[-1] if merged else None
        if (
            prev
            and not unit.speaker_change
            and len(prev.en.split()) < SHORT_UNIT_WORDS
            and not SOUND_TAG.fullmatch(prev.en)
            and not SOUND_TAG.fullmatch(unit.en)
            and len(f'{prev.en} {unit.en}'.split()) <= MERGE_MAX_WORDS
            and unit.end - prev.start <= MERGE_MAX_MS
        ):
            prev.end, prev.en = unit.end, f'{prev.en} {unit.en}'
        else:
            merged.append(unit)
    return merged


def build_request(style, text, context, title):
    """Return (llama-server path, JSON body) for one unit in the model's documented prompt format."""
    if style == 'hy-mt':
        if context:
            background = f'YouTube video "{title}". Preceding dialogue:\n' + '\n'.join(context)
            prompt = HY_MT_CONTEXT.format(background=background, text=text)
        else:
            prompt = HY_MT_PLAIN.format(text=text)
        return '/v1/chat/completions', {
            'messages': [{'role': 'user', 'content': prompt}],
            'temperature': 0.7,
            'top_p': 0.6,
            'top_k': 20,
            'repeat_penalty': 1.05,
            'max_tokens': 512,
        }
    if style == 'translategemma':
        return '/completion', {
            'prompt': TRANSLATEGEMMA.format(text=text),
            'temperature': 0,
            'n_predict': 512,
            'stop': ['<end_of_turn>'],
        }
    raise ValueError(f'unknown prompt style {style!r}; expected one of {PROMPT_STYLES}')


def parse_response(path, body):
    if path == '/completion':
        return body['content']
    return body['choices'][0]['message']['content']


def normalize(text):
    """Persian letters instead of Arabic look-alikes; single spaces; ZWNJ kept."""
    return ' '.join(text.replace('ي', 'ی').replace('ك', 'ک').split())


def wrap(text):
    """Split into at most two lines, as balanced as possible, preferring a break after punctuation."""
    if len(text) <= LINE_CHARS:
        return [text]
    words = text.split(' ')
    best = None
    for i in range(1, len(words)):
        first, second = ' '.join(words[:i]), ' '.join(words[i:])
        score = max(len(first), len(second)) - (4 if BREAK_AFTER.search(words[i - 1]) else 0)
        if best is None or score < best[0]:
            best = (score, [first, second])
    return best[1] if best else [text]


def _split(text):
    if len(text) <= CUE_CHARS:
        return [text]
    count = math.ceil(len(text) / (CUE_CHARS - 4))
    target = len(text) / count
    parts, current = [], []
    for word in text.split(' '):
        current.append(word)
        size = len(' '.join(current))
        if len(parts) < count - 1 and (size >= target or (BREAK_AFTER.search(word) and size >= 0.6 * target)):
            parts.append(' '.join(current))
            current = []
    if current:
        parts.append(' '.join(current))
    return parts


def shape_cues(text, start, end, speaker_change):
    """json3 events for one translated unit: at most two lines per cue, time split by length."""
    parts = _split(('- ' if speaker_change else '') + text)
    total = sum(len(p) for p in parts) or 1
    cues, t = [], float(start)
    for part in parts:
        duration = (end - start) * len(part) / total
        cues.append({
            'tStartMs': round(t),
            'dDurationMs': max(1, round(duration)),
            'segs': [{'utf8': '\n'.join(wrap(part))}],
        })
        t += duration
    return cues
```

- [ ] **Step 5: Run the tests to see them pass**

Run: `cd server && uv run --python 3.13 pytest tests/test_pipeline.py -q`
Expected: `14 passed`.

- [ ] **Step 6: Commit**

```bash
cd /home/ali/Documents/ali/yt_auto_sub
git add .gitignore server/pyproject.toml server/uv.lock server/subs server/tests
git commit -m "feat(server): sentence units, prompts and cue shaping"
```

---

### Task 2: Jobs, cache, LLM client and worker

**Files:**
- Create: `server/tests/test_jobs.py`
- Create: `server/subs/jobs.py`

**Interfaces:**
- Consumes: everything `subs.pipeline` produces (Task 1).
- Produces: `subs.jobs` with `Job` (`summary() -> {'status': 'working'|'done', 'done': int, 'total': int}`, `json3() -> dict`, `next_index() -> int | None`, `context(index) -> list[str]`), `Store(cache_dir, model)` (`submit(video_id, title, asr, events, position_ms) -> dict`, `touch(video_id, position_ms) -> Job | None`, `json3(job) -> dict`, `next_work() -> (job, index, english, context)`, `record(job, index, text)`, attributes `jobs: dict[str, Job]` and `changed: threading.Condition`), `Translator(llm_url, style)` with `translate(text, context, title) -> str`, `translate_unit(translate, text, context, title, log=print, wait_s=5.0) -> str`, `work_forever(store, translate, log=print)`.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_jobs.py`:

```python
import io
import json
import threading
import urllib.error
from pathlib import Path

from subs.jobs import Store, translate_unit, work_forever

FIXTURES = Path(__file__).parent / 'fixtures'
UPLOADED = json.loads((FIXTURES / 'uploaded.json').read_text(encoding='utf-8'))['events']


def submit(store, video_id='aaaaaaaaaaa', position_ms=0, events=UPLOADED):
    return store.submit(video_id, 'Spider silk', False, events, position_ms)


def test_submit_creates_job_and_is_idempotent(tmp_path):
    store = Store(tmp_path, 'test-model')

    first = submit(store)
    again = submit(store)

    assert first == again == {'status': 'working', 'done': 0, 'total': 9}
    assert len(store.jobs) == 1


def test_new_captions_for_same_video_replace_the_job(tmp_path):
    store = Store(tmp_path, 'test-model')
    submit(store)
    store.record(store.jobs['aaaaaaaaaaa'], 0, 'الف')

    summary = submit(store, events=UPLOADED[:2])

    assert summary == {'status': 'working', 'done': 0, 'total': 1}


def test_cache_survives_restart(tmp_path):
    store = Store(tmp_path, 'test-model')
    submit(store)
    store.record(store.jobs['aaaaaaaaaaa'], 3, 'ترجمه')

    reloaded = Store(tmp_path, 'test-model')

    job = reloaded.jobs['aaaaaaaaaaa']
    assert job.fa[3] == 'ترجمه'
    assert job.summary() == {'status': 'working', 'done': 1, 'total': 9}


def test_work_starts_at_viewer_position_and_wraps(tmp_path):
    store = Store(tmp_path, 'test-model')
    submit(store, position_ms=140_000)
    job = store.jobs['aaaaaaaaaaa']

    order = []
    for _ in range(job.summary()['total']):
        work_job, index, _, _ = store.next_work()
        order.append(index)
        store.record(work_job, index, 'x')

    assert order[0] == 5
    assert sorted(order) == list(range(9))
    assert order[-5:] == [0, 1, 2, 3, 4]


def test_most_recently_requested_job_goes_first(tmp_path):
    store = Store(tmp_path, 'test-model')
    submit(store, 'aaaaaaaaaaa')
    submit(store, 'bbbbbbbbbbb')
    store.touch('aaaaaaaaaaa', None)

    job, _, _, _ = store.next_work()

    assert job.video_id == 'aaaaaaaaaaa'


def test_context_is_previous_three_units(tmp_path):
    store = Store(tmp_path, 'test-model')
    submit(store)

    context = store.jobs['aaaaaaaaaaa'].context(4)

    assert len(context) == 3
    assert context[-1] == "I then started pulling out the dragline silk by hand."


def test_json3_contains_only_translated_units(tmp_path):
    store = Store(tmp_path, 'test-model')
    submit(store)
    job = store.jobs['aaaaaaaaaaa']
    store.record(job, 1, 'ما یک عنکبوت معمولی را برداشتیم.')

    result = store.json3(job)

    assert result['wireMagic'] == 'pb3'
    assert [e['segs'][0]['utf8'] for e in result['events']] == ['ما یک عنکبوت معمولی را برداشتیم.']
    assert result['events'][0]['tStartMs'] == job.units[1].start


def test_translate_unit_returns_model_text():
    assert translate_unit(lambda *a: 'سلام', 'Hi', [], '') == 'سلام'


def test_translate_unit_keeps_english_after_two_empty_answers():
    calls, logs = [], []

    def empty(*args):
        calls.append(args)
        return ''

    assert translate_unit(empty, 'Hi', [], '', log=logs.append) == 'Hi'
    assert len(calls) == 2
    assert 'keeping English' in logs[0]


def test_translate_unit_waits_while_model_is_loading_or_unreachable():
    answers = [
        urllib.error.HTTPError('http://llm', 503, 'Loading model', {}, io.BytesIO()),
        urllib.error.URLError(ConnectionRefusedError()),
        'سلام',
    ]

    def flaky(*args):
        answer = answers.pop(0)
        if isinstance(answer, Exception):
            raise answer
        return answer

    assert translate_unit(flaky, 'Hi', [], '', log=lambda m: None, wait_s=0) == 'سلام'


def test_translate_unit_counts_timeouts_as_failures():
    def slow(*args):
        raise TimeoutError('read timed out')

    assert translate_unit(slow, 'Hi', [], '', log=lambda m: None) == 'Hi'


def test_worker_translates_every_unit(tmp_path):
    store = Store(tmp_path, 'test-model')
    submit(store)
    job = store.jobs['aaaaaaaaaaa']
    threading.Thread(target=work_forever, args=(store, lambda t, c, title: f'fa:{t}'), daemon=True).start()

    with store.changed:
        assert store.changed.wait_for(lambda: job.status == 'done', timeout=5)

    assert job.fa[0].startswith('fa:we wanted')
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `cd server && uv run --python 3.13 pytest tests/test_jobs.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'subs.jobs'`.

- [ ] **Step 3: Implement**

`server/subs/jobs.py`:

```python
"""Per-video translation jobs: JSON cache, priority order, LLM client and worker loop."""

import hashlib
import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict

from .pipeline import PROMPT_STYLES, Unit, build_request, build_units, normalize, parse_response, shape_cues

CONTEXT_UNITS = 3
LLM_TIMEOUT_S = 120
MAX_FAILURES = 2


class Job:
    def __init__(self, video_id, title, source, units, fa=None, position_ms=0, model=''):
        self.video_id = video_id
        self.title = title
        self.source = source
        self.units = units
        self.fa = fa if fa is not None else [None] * len(units)
        self.position_ms = position_ms
        self.model = model
        self.requested_at = time.monotonic()

    @property
    def done(self):
        return sum(1 for text in self.fa if text is not None)

    @property
    def status(self):
        return 'done' if self.done == len(self.units) else 'working'

    def summary(self):
        return {'status': self.status, 'done': self.done, 'total': len(self.units)}

    def next_index(self):
        """First untranslated unit still ahead of the viewer, else the first untranslated one."""
        pending = [i for i, text in enumerate(self.fa) if text is None]
        if not pending:
            return None
        return next((i for i in pending if self.units[i].end > self.position_ms), pending[0])

    def context(self, index):
        previous = self.units[max(0, index - CONTEXT_UNITS):index]
        return [('- ' if u.speaker_change else '') + u.en for u in previous]

    def json3(self):
        events = []
        for unit, text in zip(self.units, self.fa):
            if text is not None:
                events += shape_cues(text, unit.start, unit.end, unit.speaker_change)
        return {'wireMagic': 'pb3', 'events': events}

    def to_dict(self):
        return {
            'video_id': self.video_id,
            'title': self.title,
            'source': self.source,
            'model': self.model,
            'position_ms': self.position_ms,
            'units': [asdict(u) for u in self.units],
            'fa': self.fa,
        }

    @classmethod
    def from_dict(cls, data):
        return cls(
            data['video_id'], data['title'], data['source'],
            [Unit(**u) for u in data['units']], data['fa'], data['position_ms'], data['model'],
        )


class Store:
    """All jobs, guarded by one condition variable; every change is written to CACHE_DIR."""

    def __init__(self, cache_dir, model):
        self.cache_dir = cache_dir
        self.model = model
        self.jobs = {}
        self.changed = threading.Condition()
        os.makedirs(cache_dir, exist_ok=True)
        for name in sorted(os.listdir(cache_dir)):
            if name.endswith('.json'):
                with open(os.path.join(cache_dir, name), encoding='utf-8') as f:
                    job = Job.from_dict(json.load(f))
                self.jobs[job.video_id] = job

    def submit(self, video_id, title, asr, events, position_ms):
        source = hashlib.sha256(json.dumps(events, sort_keys=True).encode()).hexdigest()[:16]
        with self.changed:
            job = self.jobs.get(video_id)
            if job is None or job.source != source:
                job = Job(video_id, title, source, build_units(events, asr), model=self.model)
                self.jobs[video_id] = job
                self._save(job)
            self._touch(job, position_ms)
            return job.summary()

    def touch(self, video_id, position_ms):
        with self.changed:
            job = self.jobs.get(video_id)
            if job is not None:
                self._touch(job, position_ms)
            return job

    def json3(self, job):
        with self.changed:
            return job.json3()

    def next_work(self):
        """Block until there is work; return (job, index, english, context) for the most recently requested job."""
        with self.changed:
            while True:
                pending = [j for j in self.jobs.values() if j.status != 'done']
                if pending:
                    job = max(pending, key=lambda j: j.requested_at)
                    index = job.next_index()
                    return job, index, job.units[index].en, job.context(index)
                self.changed.wait()

    def record(self, job, index, text):
        with self.changed:
            job.fa[index] = text
            self._save(job)
            self.changed.notify_all()

    def _touch(self, job, position_ms):
        if position_ms is not None:
            job.position_ms = position_ms
        job.requested_at = time.monotonic()
        self.changed.notify_all()

    def _save(self, job):
        path = os.path.join(self.cache_dir, f'{job.video_id}.json')
        with open(path + '.tmp', 'w', encoding='utf-8') as f:
            json.dump(job.to_dict(), f, ensure_ascii=False)
        os.replace(path + '.tmp', path)


class Translator:
    """llama-server client for one prompt style."""

    def __init__(self, llm_url, style):
        if style not in PROMPT_STYLES:
            raise SystemExit(f'PROMPT_STYLE must be one of {PROMPT_STYLES}, got {style!r}')
        self.llm_url = llm_url.rstrip('/')
        self.style = style

    def translate(self, text, context, title):
        path, body = build_request(self.style, text, context, title)
        request = urllib.request.Request(
            self.llm_url + path, data=json.dumps(body).encode(), headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(request, timeout=LLM_TIMEOUT_S) as response:
            return normalize(parse_response(path, json.load(response)))


def translate_unit(translate, text, context, title, log=print, wait_s=5.0):
    """Translate one unit. Wait while the model is unreachable or loading; keep English after two bad answers."""
    failures = 0
    while True:
        try:
            result = translate(text, context, title)
        except urllib.error.HTTPError as error:
            if error.code == 503:
                log('LLM is loading; waiting')
                time.sleep(wait_s)
                continue
            problem = error
        except urllib.error.URLError as error:
            if not isinstance(error.reason, TimeoutError):
                log(f'LLM unreachable ({error.reason}); waiting')
                time.sleep(wait_s)
                continue
            problem = error
        except (TimeoutError, ValueError, KeyError, IndexError) as error:
            problem = error
        else:
            if result:
                return result
            problem = ValueError('empty translation')
        failures += 1
        if failures >= MAX_FAILURES:
            log(f'keeping English for {text[:40]!r}: {problem}')
            return text


def work_forever(store, translate, log=print):
    while True:
        job, index, text, context = store.next_work()
        store.record(job, index, translate_unit(translate, text, context, job.title, log))
```

- [ ] **Step 4: Run the tests to see them pass**

Run: `cd server && uv run --python 3.13 pytest -q`
Expected: `26 passed`.

- [ ] **Step 5: Commit**

```bash
git add server/subs/jobs.py server/tests/test_jobs.py
git commit -m "feat(server): translation jobs with cache, priority and worker"
```

---

### Task 3: HTTP API with credentialed CORS

**Files:**
- Create: `server/tests/test_app.py`
- Create: `server/subs/app.py`

**Interfaces:**
- Consumes: `Store`, `Translator`, `work_forever` (Task 2).
- Produces: `subs.app` with `make_handler(store, model)`, `parse_job(payload) -> dict` (keyword arguments for `Store.submit`) and `main()`; entry point `python -m subs.app` configured by `LLM_URL`, `PROMPT_STYLE`, `MODEL_NAME`, `PORT`, `CACHE_DIR`.
  HTTP: `POST /v1/jobs` → 202 summary; `GET /v1/timedtext?v=&t=` → json3; `GET /v1/status?v=&t=` → summary; `GET /healthz` → `{model}`; `OPTIONS` → 204.

- [ ] **Step 1: Write the failing tests**

`server/tests/test_app.py`:

```python
import http.client
import json
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from subs.app import make_handler, parse_job
from subs.jobs import Store

FIXTURES = Path(__file__).parent / 'fixtures'
UPLOADED = json.loads((FIXTURES / 'uploaded.json').read_text(encoding='utf-8'))['events']
YOUTUBE = 'https://www.youtube.com'
PLAYER_HEADERS = (
    'x-goog-visitor-id,x-youtube-ad-signals,x-youtube-client-name,x-youtube-client-version,'
    'x-youtube-page-cl,x-youtube-page-label,x-youtube-time-zone,x-youtube-utc-offset'
)


@pytest.fixture
def server(tmp_path):
    store = Store(tmp_path, 'test-model')
    httpd = ThreadingHTTPServer(('127.0.0.1', 0), make_handler(store, 'test-model'))
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    yield store, httpd.server_address[1]
    httpd.shutdown()


def call(port, method, path, body=None, headers=None):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
    data = None if body is None else (body if isinstance(body, bytes) else json.dumps(body).encode())
    conn.request(method, path, body=data, headers=headers or {})
    response = conn.getresponse()
    raw = response.read()
    return response.status, dict(response.getheaders()), json.loads(raw) if raw else None


def job_body(**overrides):
    return {'videoId': 'aaaaaaaaaaa', 'title': 'Spider silk', 'track': {'languageCode': 'en', 'kind': ''},
            'positionMs': 0, 'events': UPLOADED, **overrides}


def test_credentialed_preflight_from_the_player_is_allowed(server):
    _, port = server

    status, headers, _ = call(port, 'OPTIONS', '/v1/timedtext?v=aaaaaaaaaaa', headers={
        'Origin': YOUTUBE, 'Access-Control-Request-Method': 'GET',
        'Access-Control-Request-Headers': PLAYER_HEADERS, 'Access-Control-Request-Private-Network': 'true',
    })

    assert status == 204
    assert headers['Access-Control-Allow-Origin'] == YOUTUBE
    assert headers['Access-Control-Allow-Credentials'] == 'true'
    assert headers['Access-Control-Allow-Headers'] == PLAYER_HEADERS
    assert headers['Access-Control-Allow-Private-Network'] == 'true'


def test_submit_then_status(server):
    _, port = server

    status, headers, body = call(port, 'POST', '/v1/jobs', job_body(), {'Origin': YOUTUBE, 'Content-Type': 'application/json'})

    assert status == 202
    assert body == {'status': 'working', 'done': 0, 'total': 9}
    assert headers['Access-Control-Allow-Origin'] == YOUTUBE
    assert call(port, 'GET', '/v1/status?v=aaaaaaaaaaa&t=5000')[2] == body


def test_timedtext_returns_translated_cues_and_updates_position(server):
    store, port = server
    call(port, 'POST', '/v1/jobs', job_body())
    job = store.jobs['aaaaaaaaaaa']
    store.record(job, 0, 'ما می‌خواستیم آزمایشی انجام دهیم.')

    status, headers, body = call(port, 'GET', '/v1/timedtext?v=aaaaaaaaaaa&t=131000', headers={'Origin': YOUTUBE})

    assert status == 200
    assert headers['Content-Type'] == 'application/json; charset=UTF-8'
    assert body['events'][0]['segs'][0]['utf8'] == 'ما می‌خواستیم آزمایشی انجام دهیم.'
    assert job.position_ms == 131000


def test_unknown_video_is_404(server):
    _, port = server

    assert call(port, 'GET', '/v1/timedtext?v=bbbbbbbbbbb')[0] == 404
    assert call(port, 'GET', '/v1/status?v=not-an-id')[0] == 404


def test_bad_job_is_400(server):
    _, port = server

    status, _, body = call(port, 'POST', '/v1/jobs', job_body(videoId='../../etc'))

    assert status == 400
    assert 'videoId' in body['error']


def test_empty_body_is_413(server):
    _, port = server

    assert call(port, 'POST', '/v1/jobs', b'')[0] == 413


def test_healthz_reports_model(server):
    _, port = server

    assert call(port, 'GET', '/healthz')[2] == {'model': 'test-model'}


def test_parse_job_reads_asr_kind_and_position():
    job = parse_job(job_body(track={'languageCode': 'en', 'kind': 'asr'}, positionMs=61000))

    assert job['asr'] is True
    assert job['position_ms'] == 61000


@pytest.mark.parametrize('events', [None, 'x', [1], [{'tStartMs': 'soon', 'segs': []}], [{'segs': [{'utf8': 'x'}]}]])
def test_parse_job_rejects_malformed_events(events):
    with pytest.raises(ValueError, match='events'):
        parse_job(job_body(events=events))
```

- [ ] **Step 2: Run the tests to see them fail**

Run: `cd server && uv run --python 3.13 pytest tests/test_app.py -q`
Expected: collection error `ModuleNotFoundError: No module named 'subs.app'`.

- [ ] **Step 3: Implement**

`server/subs/app.py`:

```python
"""HTTP API for the TV app. Run with `python -m subs.app`."""

import json
import os
import re
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from .jobs import Store, Translator, work_forever

VIDEO_ID = re.compile(r'^[A-Za-z0-9_-]{11}$')
MAX_BODY_BYTES = 8 * 1024 * 1024


def _int_or_none(value):
    return int(value) if isinstance(value, str) and value.isdigit() else value if isinstance(value, int) else None


def _valid_events(events):
    if not isinstance(events, list):
        return False
    for event in events:
        if not isinstance(event, dict) or not isinstance(event.get('tStartMs', 0), int):
            return False
        segs = event.get('segs', [])
        if not isinstance(segs, list) or not all(isinstance(s, dict) and isinstance(s.get('utf8', ''), str) for s in segs):
            return False
        if segs and 'tStartMs' not in event:
            return False
    return True


def parse_job(payload):
    """Validate a POST /v1/jobs body; return Store.submit keyword arguments or raise ValueError."""
    if not isinstance(payload, dict):
        raise ValueError('body must be a JSON object')
    video_id = payload.get('videoId')
    if not isinstance(video_id, str) or not VIDEO_ID.match(video_id):
        raise ValueError('videoId must be an 11-character YouTube id')
    events = payload.get('events')
    if not _valid_events(events):
        raise ValueError('events must be json3 caption events')
    track = payload.get('track') if isinstance(payload.get('track'), dict) else {}
    return {
        'video_id': video_id,
        'title': str(payload.get('title') or '')[:200],
        'asr': track.get('kind') == 'asr',
        'events': events,
        'position_ms': _int_or_none(payload.get('positionMs')) or 0,
    }


def make_handler(store, model):
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code, body=None):
            data = b'' if body is None else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            origin = self.headers.get('Origin')
            self.send_header('Access-Control-Allow-Origin', origin or '*')
            if origin:
                self.send_header('Access-Control-Allow-Credentials', 'true')
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
            self.send_header(
                'Access-Control-Allow-Headers', self.headers.get('Access-Control-Request-Headers') or 'Content-Type'
            )
            self.send_header('Access-Control-Allow-Private-Network', 'true')
            self.send_header('Vary', 'Origin')
            if body is not None:
                self.send_header('Content-Type', 'application/json; charset=UTF-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_OPTIONS(self):
            self._send(204)

        def do_GET(self):
            url = urlsplit(self.path)
            if url.path == '/healthz':
                return self._send(200, {'model': model})
            if url.path not in ('/v1/timedtext', '/v1/status'):
                return self._send(404, {'error': 'not found'})
            query = parse_qs(url.query)
            video_id = query.get('v', [''])[0]
            job = store.touch(video_id, _int_or_none(query.get('t', [None])[0])) if VIDEO_ID.match(video_id) else None
            if job is None:
                return self._send(404, {'error': 'unknown video'})
            self._send(200, store.json3(job) if url.path == '/v1/timedtext' else job.summary())

        def do_POST(self):
            if urlsplit(self.path).path != '/v1/jobs':
                return self._send(404, {'error': 'not found'})
            length = _int_or_none(self.headers.get('Content-Length')) or 0
            if not 0 < length <= MAX_BODY_BYTES:
                return self._send(413, {'error': f'body must be 1..{MAX_BODY_BYTES} bytes'})
            try:
                job = parse_job(json.loads(self.rfile.read(length)))
            except ValueError as error:
                return self._send(400, {'error': str(error)})
            self._send(202, store.submit(**job))

    return Handler


def main():
    model = os.environ.get('MODEL_NAME', 'unknown')
    translator = Translator(os.environ.get('LLM_URL', 'http://127.0.0.1:8080'), os.environ.get('PROMPT_STYLE', 'hy-mt'))
    store = Store(os.environ.get('CACHE_DIR', 'cache'), model)
    threading.Thread(target=work_forever, args=(store, translator.translate), daemon=True).start()
    port = int(os.environ.get('PORT', '8765'))
    server = ThreadingHTTPServer(('0.0.0.0', port), make_handler(store, model))
    print(f'persian-subs on :{port}, model {model}, prompt style {translator.style}', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
```

- [ ] **Step 4: Run the whole suite**

Run: `cd server && uv run --python 3.13 pytest -q`
Expected: `39 passed`.

- [ ] **Step 5: Commit**

```bash
git add server/subs/app.py server/tests/test_app.py
git commit -m "feat(server): HTTP API with credentialed CORS for the TV player"
```

---

### Task 4: Docker packaging and smoke test

**Files:**
- Create: `server/Dockerfile`, `server/.dockerignore`, `server/docker-compose.yml`, `server/gpu.yaml`, `server/pc.env`, `server/thinkpad.env`, `server/smoke.py`

**Interfaces:**
- Consumes: `python -m subs.app` and its environment variables (Task 3).
- Produces: `docker compose --env-file pc.env -f docker-compose.yml -f gpu.yaml up -d --build` (PC) and `docker compose --env-file thinkpad.env up -d --build` (ThinkPad), with `MODELS_DIR` (default `./models`) and `CACHE_DIR` (default `./cache`) overridable from the shell; `python3 smoke.py [base_url]` exits non-zero on failure.

- [ ] **Step 1: Write the smoke test**

`server/smoke.py`:

```python
"""Check a running server end to end: python3 smoke.py [http://host:8765]"""

import json
import sys
import time
import urllib.request

BASE = (sys.argv[1] if len(sys.argv) > 1 else 'http://127.0.0.1:8765').rstrip('/')
VIDEO = 'smoketest01'
EVENTS = [
    {'tStartMs': 0, 'dDurationMs': 2500, 'segs': [{'utf8': 'We wanted to run a test,'}]},
    {'tStartMs': 2500, 'dDurationMs': 2500, 'segs': [{'utf8': "but getting the sample isn't so easy."}]},
    {'tStartMs': 5000, 'dDurationMs': 3000, 'segs': [{'utf8': "It's so light that you can barely feel it."}]},
]


def call(path, body=None):
    data = None if body is None else json.dumps(body).encode()
    request = urllib.request.Request(BASE + path, data=data, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(request, timeout=10) as response:
        return json.load(response)


print('health:', call('/healthz'))
print('job:', call('/v1/jobs', {'videoId': VIDEO, 'title': 'smoke test', 'track': {'kind': ''}, 'events': EVENTS}))
started = time.monotonic()
while (status := call(f'/v1/status?v={VIDEO}'))['status'] != 'done':
    if time.monotonic() - started > 600:
        sys.exit(f'FAIL: not done after 10 minutes: {status}')
    time.sleep(2)
print(f'translated {status["total"]} sentences in {time.monotonic() - started:.1f} s')
for event in call(f'/v1/timedtext?v={VIDEO}')['events']:
    print(' ', event['segs'][0]['utf8'].replace('\n', ' / '))
```

- [ ] **Step 2: Run it with no server to see it fail**

Run: `cd server && python3 smoke.py`
Expected: `urllib.error.URLError: <urlopen error [Errno 111] Connection refused>`.

- [ ] **Step 3: Write the packaging files**

`server/Dockerfile`:

```dockerfile
FROM python:3.13-slim
WORKDIR /app
COPY subs ./subs
ENV PYTHONUNBUFFERED=1 PORT=8765 CACHE_DIR=/cache
EXPOSE 8765
CMD ["python", "-m", "subs.app"]
```

`server/.dockerignore`:

```text
*
!subs/
subs/__pycache__/
```

`server/docker-compose.yml`:

```yaml
name: persian-subs

services:
  model:
    image: curlimages/curl:8.17.0
    user: "${UID:-1000}:${GID:-1000}"
    environment:
      MODEL_URL: ${MODEL_URL:?set MODEL_URL in the env file}
      MODEL_FILE: ${MODEL_FILE:?set MODEL_FILE in the env file}
    volumes:
      - ${MODELS_DIR:-./models}:/models
    entrypoint:
      - sh
      - -c
      - >-
        if [ -s "/models/$$MODEL_FILE" ]; then echo "model present: $$MODEL_FILE"; exit 0; fi;
        curl -fL --retry 5 -C - -o "/models/$$MODEL_FILE.part" "$$MODEL_URL"
        && mv "/models/$$MODEL_FILE.part" "/models/$$MODEL_FILE"

  llm:
    image: ${LLM_IMAGE:?set LLM_IMAGE in the env file}
    depends_on:
      model:
        condition: service_completed_successfully
    volumes:
      - ${MODELS_DIR:-./models}:/models:ro
    command: -m /models/${MODEL_FILE} --host 0.0.0.0 --port 8080 -c 4096 ${LLM_ARGS:-}
    restart: unless-stopped

  subs:
    build: .
    depends_on:
      - llm
    user: "${UID:-1000}:${GID:-1000}"
    environment:
      LLM_URL: http://llm:8080
      PROMPT_STYLE: ${PROMPT_STYLE:-hy-mt}
      MODEL_NAME: ${MODEL_FILE}
    volumes:
      - ${CACHE_DIR:-./cache}:/cache
    ports:
      - "8765:8765"
    restart: unless-stopped
```

`server/gpu.yaml`:

```yaml
services:
  llm:
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu]
```

`server/pc.env`:

```text
LLM_IMAGE=ghcr.io/ggml-org/llama.cpp:server-cuda12-b11561
MODEL_URL=https://huggingface.co/tencent/Hy-MT2-7B-GGUF/resolve/main/Hy-MT2-7B-Q4_K_M.gguf
MODEL_FILE=Hy-MT2-7B-Q4_K_M.gguf
PROMPT_STYLE=hy-mt
LLM_ARGS=-ngl 99
```

`server/thinkpad.env`:

```text
LLM_IMAGE=ghcr.io/ggml-org/llama.cpp:server-b11561
MODEL_URL=https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/main/Hy-MT2-1.8B-Q4_K_M.gguf
MODEL_FILE=Hy-MT2-1.8B-Q4_K_M.gguf
PROMPT_STYLE=hy-mt
LLM_ARGS=-t 4
```

- [ ] **Step 4: Start the ThinkPad variant on this laptop and run the smoke test**

The 1.8B model from the blind test is reused so nothing is downloaded; if it is gone, drop `MODELS_DIR` and the stack downloads it (1.1 GB).

```bash
cd /home/ali/Documents/ali/yt_auto_sub/server
export MODELS_DIR=/tmp/claude-1000/-home-ali-Documents-ali-yt-auto-sub/934c3dc4-1112-483a-afe5-c46df33840ca/scratchpad/spike/models
mkdir -p cache
docker compose --env-file thinkpad.env up -d --build
python3 smoke.py
```

Expected: `health: {'model': 'Hy-MT2-1.8B-Q4_K_M.gguf'}`, then `translated 2 sentences in` about 10 s, then two Persian lines, each shown as `line one / line two`.
`docker compose --env-file thinkpad.env logs model` shows `model present: Hy-MT2-1.8B-Q4_K_M.gguf`.

- [ ] **Step 5: Check the download path with a small file**

```bash
mkdir -p /tmp/dl-test
MODELS_DIR=/tmp/dl-test MODEL_URL=https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/main/README.md MODEL_FILE=readme.test docker compose --env-file thinkpad.env run --rm model
MODELS_DIR=/tmp/dl-test MODEL_URL=https://huggingface.co/tencent/Hy-MT2-1.8B-GGUF/resolve/main/README.md MODEL_FILE=readme.test docker compose --env-file thinkpad.env run --rm model
ls -l /tmp/dl-test
```

Expected: the first run downloads, the second prints `model present: readme.test`, and `readme.test` is owned by the current user.

- [ ] **Step 6: Stop the stack and commit**

```bash
docker compose --env-file thinkpad.env down
rm -rf cache /tmp/dl-test
cd /home/ali/Documents/ali/yt_auto_sub
git add server/Dockerfile server/.dockerignore server/docker-compose.yml server/gpu.yaml server/pc.env server/thinkpad.env server/smoke.py
git commit -m "feat(server): Docker Compose stack for PC (CUDA) and ThinkPad (CPU)"
```

---

### Task 5: TV core functions

**Files:**
- Create: `youtube-webos/test/persian-ai-core.test.js`
- Create: `youtube-webos/src/persian-ai-core.ts`

**Interfaces:**
- Consumes: nothing.
- Produces: `CaptionTrack { baseUrl: string; languageCode: string; kind?: string }`, `pickEnglishTrack(tracks) -> CaptionTrack | undefined`, `englishCaptionUrl(track) -> string`, `parseServers(list: string) -> string[]`, `persianCaptionVideoId(url: string) -> string | null`, `serverCaptionUrl(server, videoId, positionMs) -> string`, `firstAccepting(servers, send: (server) => Promise<unknown>) -> Promise<string | null>`.

- [ ] **Step 1: Create the branch**

```bash
cd /home/ali/Documents/ali/yt_auto_sub/youtube-webos
git checkout -b persian-ai-subtitles persian-subtitles
```

- [ ] **Step 2: Write the failing tests**

`test/persian-ai-core.test.js`:

```js
import assert from 'node:assert/strict';
import { test } from 'node:test';

import {
  englishCaptionUrl,
  firstAccepting,
  parseServers,
  persianCaptionVideoId,
  pickEnglishTrack,
  serverCaptionUrl
} from '../src/persian-ai-core.ts';

const asr = {
  baseUrl: 'https://yt/api/timedtext?v=a&kind=asr',
  languageCode: 'en',
  kind: 'asr'
};
const uploaded = {
  baseUrl: 'https://yt/api/timedtext?v=a',
  languageCode: 'en-US'
};
const french = {
  baseUrl: 'https://yt/api/timedtext?v=a&lang=fr',
  languageCode: 'fr'
};

test('prefers uploaded English over auto-generated English', () => {
  assert.equal(pickEnglishTrack([asr, french, uploaded]), uploaded);
});

test('falls back to auto-generated English', () => {
  assert.equal(pickEnglishTrack([french, asr]), asr);
});

test('returns undefined without English', () => {
  assert.equal(pickEnglishTrack([french]), undefined);
});

test('asks for json3 exactly once', () => {
  assert.equal(
    englishCaptionUrl({
      ...uploaded,
      baseUrl: 'https://yt/api/timedtext?v=a&fmt=srv3&x=1'
    }),
    'https://yt/api/timedtext?v=a&x=1&fmt=json3'
  );
});

test('parses the build-time server list', () => {
  assert.deepEqual(
    parseServers(' http://192.168.10.139:8765/ ,,http://192.168.10.50:8765'),
    ['http://192.168.10.139:8765', 'http://192.168.10.50:8765']
  );
  assert.deepEqual(parseServers(''), []);
});

test('recognises the player Persian caption request', () => {
  const url =
    'https://www.youtube.com/api/timedtext?v=dQw4w9WgXcQ&ei=x&lang=en&tlang=fa&fmt=json3&c=TVHTML5';
  assert.equal(persianCaptionVideoId(url), 'dQw4w9WgXcQ');
});

test('ignores other caption and non-caption requests', () => {
  assert.equal(
    persianCaptionVideoId(
      'https://www.youtube.com/api/timedtext?v=dQw4w9WgXcQ&lang=en&fmt=json3'
    ),
    null
  );
  assert.equal(
    persianCaptionVideoId(
      'https://www.youtube.com/api/timedtext?v=dQw4w9WgXcQ&tlang=fr'
    ),
    null
  );
  assert.equal(
    persianCaptionVideoId(
      'https://www.youtube.com/youtubei/v1/player?tlang=fa'
    ),
    null
  );
});

test('builds the server caption URL with a whole, non-negative position', () => {
  assert.equal(
    serverCaptionUrl('http://pc:8765', 'dQw4w9WgXcQ', 61234.6),
    'http://pc:8765/v1/timedtext?v=dQw4w9WgXcQ&t=61235'
  );
  assert.equal(
    serverCaptionUrl('http://pc:8765', 'dQw4w9WgXcQ', -5),
    'http://pc:8765/v1/timedtext?v=dQw4w9WgXcQ&t=0'
  );
});

test('uses the first server that accepts the job', async () => {
  const tried = [];
  const chosen = await firstAccepting(
    ['http://pc', 'http://thinkpad'],
    async (server) => {
      tried.push(server);
      if (server === 'http://pc') throw new Error('timeout');
    }
  );
  assert.equal(chosen, 'http://thinkpad');
  assert.deepEqual(tried, ['http://pc', 'http://thinkpad']);
});

test('returns null when no server accepts', async () => {
  const chosen = await firstAccepting(['http://pc'], async () => {
    throw new Error('refused');
  });
  assert.equal(chosen, null);
});
```

- [ ] **Step 3: Run the tests to see them fail**

Run: `pnpm run test:unit`
Expected: failure with `ERR_MODULE_NOT_FOUND` for `src/persian-ai-core.ts`.

- [ ] **Step 4: Implement**

`src/persian-ai-core.ts`:

```ts
export interface CaptionTrack {
  baseUrl: string;
  languageCode: string;
  kind?: string;
}

const isEnglish = (track: CaptionTrack) =>
  track.languageCode === 'en' || track.languageCode.startsWith('en-');

export function pickEnglishTrack(
  tracks: readonly CaptionTrack[]
): CaptionTrack | undefined {
  return (
    tracks.find((t) => isEnglish(t) && t.kind !== 'asr') ??
    tracks.find((t) => isEnglish(t) && t.kind === 'asr')
  );
}

export function englishCaptionUrl(track: CaptionTrack): string {
  return track.baseUrl.replace(/&fmt=[^&]*/, '') + '&fmt=json3';
}

export function parseServers(list: string): string[] {
  return list
    .split(',')
    .map((server) => server.trim().replace(/\/+$/, ''))
    .filter(Boolean);
}

export function persianCaptionVideoId(url: string): string | null {
  if (!url.includes('/api/timedtext?') || !/[?&]tlang=fa(&|$)/.test(url)) {
    return null;
  }
  return /[?&]v=([\w-]{11})(&|$)/.exec(url)?.[1] ?? null;
}

export function serverCaptionUrl(
  server: string,
  videoId: string,
  positionMs: number
): string {
  return `${server}/v1/timedtext?v=${videoId}&t=${Math.max(0, Math.round(positionMs))}`;
}

export async function firstAccepting(
  servers: readonly string[],
  send: (server: string) => Promise<unknown>
): Promise<string | null> {
  for (const server of servers) {
    try {
      await send(server);
      return server;
    } catch {
      // `send` logs its own failure; try the next server.
    }
  }
  return null;
}
```

- [ ] **Step 5: Run the tests and lint**

Run: `pnpm run test:unit && pnpm run lint:all`
Expected: `ℹ tests 18`, `ℹ pass 18`, and lint exits 0.

- [ ] **Step 6: Commit**

```bash
git add src/persian-ai-core.ts test/persian-ai-core.test.js
git commit -m "feat: pure helpers for AI Persian subtitles"
```

---

### Task 6: TV wiring and desktop E2E

**Files:**
- Create: `e2e/tv.mjs` (shared TV harness helpers)
- Modify: `e2e/persian-subtitles.e2e.mjs` (use `tv.mjs`; behaviour unchanged)
- Create: `e2e/ai-subtitles.e2e.mjs`
- Create: `youtube-webos/src/persian-ai-subtitles.ts`
- Modify: `youtube-webos/webpack.config.js` (`DefinePlugin`)
- Modify: `youtube-webos/src/userScript.ts` (one import)

**Interfaces:**
- Consumes: Task 5 helpers; `getPlayerManager`, `PlayerMode`, `VideoID`, `YTPlayer` from `src/player_api`; the server API (Task 3).
- Produces: build-time `PERSIAN_SUBS_SERVERS` (comma-separated base URLs, priority order); console tag `[persian-ai]`.

- [ ] **Step 1: Write the shared harness and refactor the existing E2E**

`e2e/tv.mjs`:

```js
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
```

`e2e/persian-subtitles.e2e.mjs` (replace the whole file):

```js
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
```

- [ ] **Step 2: Write the failing AI E2E**

`e2e/ai-subtitles.e2e.mjs`:

```js
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
```

- [ ] **Step 3: Build the fork without the module and see the E2E fail**

```bash
cd /home/ali/Documents/ali/yt_auto_sub/youtube-webos
PERSIAN_SUBS_SERVERS="http://192.0.2.1:8765,http://$(hostname -I | awk '{print $1}'):8765" pnpm run build
cd ../e2e
node ai-subtitles.e2e.mjs
```

Expected: `FAIL: caption never matched; last: "…"` where the last caption is YouTube's own Persian.

- [ ] **Step 4: Implement the module and wire it in**

`youtube-webos/src/persian-ai-subtitles.ts`:

```ts
import {
  englishCaptionUrl,
  firstAccepting,
  parseServers,
  persianCaptionVideoId,
  pickEnglishTrack,
  serverCaptionUrl,
  type CaptionTrack
} from './persian-ai-core';
import { getPlayerManager, PlayerMode } from './player_api';
import type { VideoID, YTPlayer } from './player_api';

declare const __PERSIAN_SUBS_SERVERS__: string;

interface CaptionApi {
  getPlayerResponse():
    | {
        captions?: {
          playerCaptionsTracklistRenderer?: { captionTracks?: CaptionTrack[] };
        };
        videoDetails?: { title?: string };
      }
    | undefined;
  getCurrentTime(): number;
  getOption(
    module: 'captions',
    option: 'track'
  ): { translationLanguage?: { languageCode?: string } } | undefined;
  setOption(module: 'captions', option: 'reload', value: boolean): void;
}

interface JobStatus {
  status: 'working' | 'done';
  done: number;
}

const TAG = '[persian-ai]';
const SERVERS = parseServers(__PERSIAN_SUBS_SERVERS__);
const SUBMIT_TIMEOUT_MS = 3000;
const CAPTIONS_TIMEOUT_MS = 15000;
const POLL_MS = 10000;

const serverFor = new Map<VideoID, string>();
const submitted = new Set<VideoID>();
let player: (YTPlayer & CaptionApi) | null = null;
let poll: ReturnType<typeof setInterval> | undefined;

function request(
  method: 'GET' | 'POST',
  url: string,
  timeoutMs: number,
  body?: unknown
): Promise<unknown> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open(method, url);
    xhr.timeout = timeoutMs;
    xhr.onload = () => {
      if (xhr.status >= 200 && xhr.status < 300) {
        resolve(JSON.parse(xhr.responseText));
      } else {
        reject(new Error(`${method} ${url}: HTTP ${xhr.status}`));
      }
    };
    xhr.onerror = () => reject(new Error(`${method} ${url}: network error`));
    xhr.ontimeout = () => reject(new Error(`${method} ${url}: timeout`));
    if (body === undefined) {
      xhr.send();
    } else {
      xhr.setRequestHeader('Content-Type', 'application/json');
      xhr.send(JSON.stringify(body));
    }
  });
}

const positionMs = () => (player ? player.getCurrentTime() * 1000 : 0);

const persianActive = () =>
  player?.getOption('captions', 'track')?.translationLanguage?.languageCode ===
  'fa';

function reloadCaptions() {
  player?.setOption('captions', 'reload', true);
}

function redirect(url: string): string {
  try {
    const videoId = persianCaptionVideoId(url);
    const server = videoId ? serverFor.get(videoId) : undefined;
    return videoId && server
      ? serverCaptionUrl(server, videoId, positionMs())
      : url;
  } catch (error) {
    console.warn(TAG, 'leaving caption request unchanged:', error);
    return url;
  }
}

const originalOpen = XMLHttpRequest.prototype.open as (
  this: XMLHttpRequest,
  method: string,
  url: string | URL,
  async?: boolean,
  username?: string | null,
  password?: string | null
) => void;

XMLHttpRequest.prototype.open = function (
  this: XMLHttpRequest,
  method: string,
  url: string | URL,
  async = true,
  username?: string | null,
  password?: string | null
) {
  originalOpen.call(
    this,
    method,
    redirect(String(url)),
    async,
    username,
    password
  );
} as typeof XMLHttpRequest.prototype.open;

function stopPolling() {
  if (poll !== undefined) clearInterval(poll);
  poll = undefined;
}

function startPolling(videoId: VideoID, server: string) {
  stopPolling();
  let lastDone = 0;
  poll = setInterval(() => {
    if (playerManager.currentVideoID !== videoId) {
      stopPolling();
      return;
    }
    if (!persianActive()) return;
    request(
      'GET',
      `${server}/v1/status?v=${videoId}&t=${Math.round(positionMs())}`,
      SUBMIT_TIMEOUT_MS
    )
      .then((result) => {
        const status = result as JobStatus;
        if (status.done > lastDone) reloadCaptions();
        lastDone = status.done;
        if (status.status === 'done') stopPolling();
      })
      .catch((error: unknown) => console.warn(TAG, error));
  }, POLL_MS);
}

async function submit(videoId: VideoID) {
  const response = player?.getPlayerResponse();
  const track = pickEnglishTrack(
    response?.captions?.playerCaptionsTracklistRenderer?.captionTracks ?? []
  );
  if (!track) return;

  const captions = (await request(
    'GET',
    englishCaptionUrl(track),
    CAPTIONS_TIMEOUT_MS
  )) as { events?: unknown[] };
  const job = {
    videoId,
    title: response?.videoDetails?.title ?? '',
    track: { languageCode: track.languageCode, kind: track.kind ?? '' },
    positionMs: Math.round(positionMs()),
    events: captions.events ?? []
  };

  const server = await firstAccepting(SERVERS, (candidate) =>
    request('POST', `${candidate}/v1/jobs`, SUBMIT_TIMEOUT_MS, job).catch(
      (error: unknown) => {
        console.warn(TAG, error);
        throw error;
      }
    )
  );
  if (!server) {
    console.warn(TAG, 'no subtitle server accepted', videoId);
    return;
  }
  if (playerManager.currentVideoID !== videoId) return;

  serverFor.set(videoId, server);
  if (persianActive()) reloadCaptions();
  startPolling(videoId, server);
}

const playerManager = await getPlayerManager();
player = playerManager.player as YTPlayer & CaptionApi;
console.info(TAG, 'servers:', SERVERS);

playerManager.addEventListener('playbackStart', function () {
  const videoId = this.currentVideoID;
  if (!SERVERS.length || !videoId || submitted.has(videoId)) return;
  if (this.playerMode !== PlayerMode.NORMAL) return;
  submitted.add(videoId);
  submit(videoId).catch((error: unknown) => {
    submitted.delete(videoId);
    console.warn(TAG, 'could not submit', videoId, error);
  });
});
```

In `youtube-webos/webpack.config.js`, extend the existing `DefinePlugin`:

```js
      new webpack.DefinePlugin({
        __YTAF_VERSION__: JSON.stringify(pkgJson.version),
        __PERSIAN_SUBS_SERVERS__: JSON.stringify(
          process.env.PERSIAN_SUBS_SERVERS ?? ''
        )
      })
```

In `youtube-webos/src/userScript.ts`, after `import './persian-subtitles';`, add:

```ts
import './persian-ai-subtitles';
```

- [ ] **Step 5: Run the fork checks and rebuild**

```bash
cd /home/ali/Documents/ali/yt_auto_sub/youtube-webos
pnpm run lint:all && pnpm run test:unit
PERSIAN_SUBS_SERVERS="http://192.0.2.1:8765,http://$(hostname -I | awk '{print $1}'):8765" pnpm run build
pnpm run test:compat
```

Expected: lint exits 0, `ℹ pass 18`, webpack `compiled with 3 warnings` (the existing asset-size warnings), `✓ ES-Check passed!`.

- [ ] **Step 6: Run both E2E harnesses**

```bash
cd /home/ali/Documents/ali/yt_auto_sub/e2e
node ai-subtitles.e2e.mjs
node persian-subtitles.e2e.mjs
```

Expected: `PASS: AI captions, reload, failover and fallback` (with `server caption fetches:` at least 2) and `PASS: English >> Persian`.
Look at `e2e/out/ai-captions.png` and `e2e/out/fallback-captions.png`: captions sit at the bottom in the normal caption style, at most two lines.

- [ ] **Step 7: Commit in both repos**

```bash
cd /home/ali/Documents/ali/yt_auto_sub/youtube-webos
git add src/persian-ai-subtitles.ts src/userScript.ts webpack.config.js
git commit -m "feat: AI Persian subtitles from a LAN server with fallback to YouTube"
cd ..
git add e2e/tv.mjs e2e/persian-subtitles.e2e.mjs e2e/ai-subtitles.e2e.mjs
git commit -m "test(e2e): AI subtitles harness with fake model, failover and fallback"
```

---

### Task 7: README, TV package and delivery to the PC

**Files:**
- Modify: `README.md` (replace the whole file)
- Build: `youtube-webos/youtube.leanback.v4_0.5.3_all.ipk`
- Copy to the PC: `~/persian-subs/` (the `server/` folder) and `~/youtube.leanback.v4_0.5.3_all.ipk`

**Interfaces:**
- Consumes: everything above; `THINKPAD_IP` from the user.
- Produces: the install guide and the artefacts the user installs.

- [ ] **Step 1: Write the README**

Replace `README.md` with the following, then replace `THINKPAD_IP` with the user's address: `sed -i "s/THINKPAD_IP/<address>/g" README.md`.

````markdown
# YouTube AdFree with AI Persian subtitles

A personal build of [webosbrew/youtube-webos](https://github.com/webosbrew/youtube-webos) plus a small home server.
Pick **Persian** under **Settings → Captions → Auto-translated**, and the TV shows Persian subtitles translated by a local AI model on the PC, or on the ThinkPad when the PC is off.
If neither machine answers, the TV shows YouTube's own Persian translation.

- Designs: `docs/superpowers/specs/2026-10-12-persian-auto-translate-subtitles-design.md`, `docs/superpowers/specs/2026-10-12-ai-persian-subtitles-design.md`
- Plans: `docs/superpowers/plans/2026-10-12-persian-auto-translate-subtitles.md`, `docs/superpowers/plans/2026-10-12-ai-persian-subtitles.md`
- TV app source: `youtube-webos/` (branch `persian-ai-subtitles`)
- Server: `server/`

## How it works

When a video starts, the TV app sends the video's English captions to the PC (`192.168.10.139`), or to the ThinkPad (`THINKPAD_IP`) if the PC does not answer within 3 seconds.
That machine translates them sentence by sentence with a local model, starting at the point you are watching.
When you pick Persian, the TV loads the translated subtitles from that machine and refreshes them every 10 seconds until the whole video is done.

## 1. Install the server

Each machine runs the same Docker setup from the `server/` folder.
The folder is already at `~/persian-subs` on the PC.
Copy it to the ThinkPad with `scp -r ~/persian-subs ali@THINKPAD_IP:`.

### PC on Linux (NVIDIA GPU)

1. Install Docker and the NVIDIA Container Toolkit, then log out and back in:

   ```bash
   sudo pacman -S docker docker-compose nvidia-container-toolkit
   sudo nvidia-ctk runtime configure --runtime=docker
   sudo systemctl enable --now docker
   sudo usermod -aG docker "$USER"
   ```

2. If you already downloaded `Hy-MT2-7B-Q4_K_M.gguf`, move it to `~/persian-subs/models/` (create the folder first).
   Otherwise the first start downloads it (4.6 GB).
3. Start the server:

   ```bash
   cd ~/persian-subs
   mkdir -p models cache
   docker compose --env-file pc.env -f docker-compose.yml -f gpu.yaml up -d --build
   ```

   `docker compose --env-file pc.env logs -f model llm` shows the download and the model loading.
4. Check it: `python3 smoke.py` prints `translated 2 sentences` and two Persian lines.

### ThinkPad (CPU)

1. Install Docker, then log out and back in:

   ```bash
   sudo pacman -S docker docker-compose
   sudo systemctl enable --now docker
   sudo usermod -aG docker "$USER"
   ```

2. Start the server and check it:

   ```bash
   cd ~/persian-subs
   mkdir -p models cache
   docker compose --env-file thinkpad.env up -d --build
   python3 smoke.py
   ```

### PC on Windows

1. Install [Docker Desktop](https://docs.docker.com/desktop/setup/install/windows-install/) with the WSL 2 backend, and a current NVIDIA driver.
   In Docker Desktop settings, turn on "Start Docker Desktop when you sign in", so the server comes back after a reboot.
2. Copy the `server` folder to the Windows side, for example `D:\persian-subs`.
3. To avoid downloading the model a second time, copy `Hy-MT2-7B-Q4_K_M.gguf` into `D:\persian-subs\models\`.
4. In PowerShell, in that folder:

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
To rebuild on the laptop:

```bash
cd youtube-webos
git fetch origin && git rebase origin/main
pnpm install
pnpm run lint:all && pnpm run test:unit
PERSIAN_SUBS_SERVERS="http://192.0.2.1:8765,http://$(hostname -I | awk '{print $1}'):8765" pnpm run build
cd ../e2e && npm install && npx playwright install chromium
node persian-subtitles.e2e.mjs && node ai-subtitles.e2e.mjs
cd ../youtube-webos
PERSIAN_SUBS_SERVERS="http://192.168.10.139:8765,http://THINKPAD_IP:8765" pnpm run build
pnpm run test:compat && pnpm run package
```

The E2E build points at an unreachable address first and this laptop second, so the test covers failover.
Server tests: `cd server && uv run --python 3.13 pytest`.
````

- [ ] **Step 2: Build the TV package with the real addresses**

```bash
cd /home/ali/Documents/ali/yt_auto_sub/youtube-webos
PERSIAN_SUBS_SERVERS="http://192.168.10.139:8765,http://<address>:8765" pnpm run build
pnpm run test:compat && pnpm run package
grep -c "192.168.10.139:8765" dist/webOSUserScripts/userScript.js
```

Expected: `✓ ES-Check passed!`, the `.ipk` is written, and `grep` prints `1`.

- [ ] **Step 3: Copy the server folder and the package to the PC**

```bash
cd /home/ali/Documents/ali/yt_auto_sub
rsync -a --delete --exclude models --exclude cache --exclude .venv --exclude __pycache__ --exclude .pytest_cache \
  -e "ssh -i ~/.ssh/id_ed25519_pc_spike" server/ ali@ali:persian-subs/
scp -i ~/.ssh/id_ed25519_pc_spike youtube-webos/youtube.leanback.v4_0.5.3_all.ipk ali@ali:
ssh -i ~/.ssh/id_ed25519_pc_spike ali@ali 'ls ~/persian-subs ~/youtube.leanback.v4_0.5.3_all.ipk'
```

Expected: the listing shows `Dockerfile docker-compose.yml gpu.yaml pc.env pyproject.toml smoke.py subs tests thinkpad.env uv.lock` and the `.ipk`.

- [ ] **Step 4: Commit**

```bash
git add README.md
git commit -m "docs: install guide for the AI subtitle server and TV build"
```

## After the plan (user, then Claude)

1. The user installs Docker on the PC, ThinkPad and Windows, starts the stacks and installs the `.ipk`, following the README.
2. Claude verifies the PC over SSH: `docker compose --env-file pc.env ps`, `python3 ~/persian-subs/smoke.py`, and the translation speed of one 10-minute video.
3. The user runs the TV checklist in the README.
4. When the blind test picks the models, only `MODEL_URL`, `MODEL_FILE` and `PROMPT_STYLE` in `pc.env` and `thinkpad.env` change.
