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
