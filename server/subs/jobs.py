"""Per-video translation jobs: JSON cache, priority order, LLM client and worker loop."""

import hashlib
import http.client
import json
import os
import threading
import time
import urllib.error
import urllib.request
from dataclasses import asdict

from .pipeline import (
    PROMPT_STYLES,
    Unit,
    build_request,
    build_units,
    normalize,
    parse_response,
    shape_cues,
)

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
                if job.model == model:
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
        except (TimeoutError, ConnectionError, http.client.HTTPException, ValueError, KeyError, IndexError) as error:
            problem = error
        else:
            if result:
                return result
            problem = ValueError('empty translation')
        failures += 1
        if failures >= MAX_FAILURES:
            log(f'keeping English for {text[:40]!r}: {problem}')
            return text


def work_forever(store, translate, log=print, wait_s=5.0):
    while True:
        try:
            job, index, text, context = store.next_work()
            store.record(job, index, translate_unit(translate, text, context, job.title, log, wait_s))
        except Exception as error:  # noqa: BLE001 - the worker must outlive any bad job
            log(f'worker error, retrying: {error!r}')
            time.sleep(wait_s)
