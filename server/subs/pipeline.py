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
