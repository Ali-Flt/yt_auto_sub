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
        raise ValueError('body must be a JSON object')  # noqa: TRY004 - the handler answers ValueError with 400
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
