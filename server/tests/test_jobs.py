import http.client
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
        urllib.error.HTTPError('http://llm', 503, 'Loading model', {}, io.BytesIO()),
        urllib.error.URLError(ConnectionRefusedError()),
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


def test_translate_unit_counts_dropped_connections_as_failures():
    answers = [http.client.RemoteDisconnected('closed'), http.client.IncompleteRead(b'')]

    def dropping(*args):
        raise answers.pop(0)

    assert translate_unit(dropping, 'Hi', [], '', log=lambda m: None) == 'Hi'


def test_worker_survives_unexpected_errors(tmp_path):
    store = Store(tmp_path, 'test-model')
    submit(store)
    job = store.jobs['aaaaaaaaaaa']
    calls = []

    def flaky(text, context, title):
        calls.append(text)
        if len(calls) == 1:
            raise RuntimeError('boom')
        return f'fa:{text}'

    threading.Thread(target=work_forever, args=(store, flaky), kwargs={'log': lambda m: None, 'wait_s': 0}, daemon=True).start()

    with store.changed:
        assert store.changed.wait_for(lambda: job.status == 'done', timeout=5)


def test_cache_from_another_model_is_ignored(tmp_path):
    old = Store(tmp_path, 'old-model')
    submit(old)
    old.record(old.jobs['aaaaaaaaaaa'], 0, 'ترجمه قدیمی')

    new = Store(tmp_path, 'new-model')

    assert new.jobs == {}
    assert submit(new) == {'status': 'working', 'done': 0, 'total': 9}
