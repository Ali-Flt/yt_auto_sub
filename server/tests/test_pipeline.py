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
    text = 'ما می‌خواستیم یک آزمایش انجام دهیم، اما معلوم شد که تهیه نمونه چندان آسان نیست.'

    lines = wrap(text)

    assert lines == ['ما می‌خواستیم یک آزمایش انجام دهیم،', 'اما معلوم شد که تهیه نمونه چندان آسان نیست.']


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


def test_shape_cues_never_exceeds_two_lines_of_42_characters():
    text = (
        'و این بدان معناست که با توجه به جرم و طول یکسان، تار عنکبوت\u200cها می\u200cتوانند تقریباً دو برابر '
        'نیروی مورد نیاز برای شکستن فولاد فوق\u200cالعاده مقاوم را تحمل کنند.'
    )

    cues = shape_cues(text, 0, 10000, speaker_change=False)

    cue_lines = [c['segs'][0]['utf8'].split('\n') for c in cues]
    lines = [line for pair in cue_lines for line in pair]
    assert all(len(pair) <= 2 for pair in cue_lines)
    assert all(len(pair[-1]) <= 42 for pair in cue_lines)
    assert all(len(pair[0]) <= (46 if len(pair) == 2 and pair[0][-1] in '،,.؛؟!:' else 42) for pair in cue_lines)
    assert ' '.join(lines) == text
    assert sum(c['dDurationMs'] for c in cues) == 10000
