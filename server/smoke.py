"""Check a running server end to end: python3 smoke.py [http://host:8765]"""

import json
import sys
import time
import urllib.error
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


for attempt in range(30):
    try:
        print('health:', call('/healthz'))
        break
    except (urllib.error.URLError, ConnectionError):
        if attempt == 29:
            raise
        time.sleep(2)
print('job:', call('/v1/jobs', {'videoId': VIDEO, 'title': 'smoke test', 'track': {'kind': ''}, 'events': EVENTS}))
started = time.monotonic()
while (status := call(f'/v1/status?v={VIDEO}'))['status'] != 'done':
    if time.monotonic() - started > 600:
        sys.exit(f'FAIL: not done after 10 minutes: {status}')
    time.sleep(2)
print(f'translated {status["total"]} sentences in {time.monotonic() - started:.1f} s')
for event in call(f'/v1/timedtext?v={VIDEO}')['events']:
    print(' ', event['segs'][0]['utf8'].replace('\n', ' / '))
