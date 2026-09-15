"""State primitives. Confirmation is a workflow record, not host authentication."""
import contextlib
import fcntl
import hashlib
import json
import os
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
class WorkflowError(Exception):
    pass

def require(condition, message):
    if not condition:
        raise WorkflowError(message)

def uid(prefix='r'):
    return prefix + uuid.uuid4().hex[:12]

def digest(data):
    return hashlib.sha256(data).hexdigest()

def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()

def sha_file(path):
    require(Path(path).is_file(), f'MISSING_FILE: {path}; restore the project files')
    return digest(Path(path).read_bytes())

def read_json(path):
    try:
        return json.loads(Path(path).read_text())
    except (OSError, ValueError) as exc:
        raise WorkflowError(f'INVALID_JSON: {path}: {exc}') from exc

def atomic_json(path, data):
    path = Path(path)
    temp = path.with_name(path.name + '.' + uuid.uuid4().hex + '.tmp')
    with temp.open('wb') as f:
        f.write(canonical(data)); f.flush(); os.fsync(f.fileno())
    os.replace(temp, path)

@contextlib.contextmanager
def locked(project):
    project = Path(project)
    require(project.is_dir(), 'PROJECT_MISSING: restore the full working directory')
    with (project / '.lock').open('a') as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        yield

def load(project):
    s = read_json(Path(project) / 'state.json')
    require(s.get('schema_version') == 1, 'STATE_SCHEMA: unsupported state version')
    return s

def save(project, s):
    atomic_json(Path(project) / 'state.json', s)

def artifact(project, revision, kind, path, grid_sha=None, params=None):
    return {'revision_id': revision, 'kind': kind, 'path': str(Path(path).relative_to(project)),
            'sha256': sha_file(path), 'grid_sha256': grid_sha, 'params': params or {},
            'status': 'ready', 'created_at': time.time()}

def checked_file(project, record):
    path = (Path(project) / record['path']).resolve()
    require(path.is_relative_to(Path(project).resolve()), 'FILE_PATH: outside project')
    require(sha_file(path) == record['sha256'], f'CORRUPT_FILE: {path}')
    return path

def current(s, revision=None):
    r = revision or s['current_revision']
    require(r in s['revisions'], 'REVISION_MISSING')
    return s['revisions'][r]

def confirmed(rev, stage):
    record = rev['confirmations'].get(stage)
    if not record or record['revision_id'] != rev['revision_id']:
        return False
    if stage in ('pixel', 'png') and record.get('grid_sha256') != rev.get('grid_sha256'):
        return False
    if stage == 'png' and record.get('artifact_sha256') != rev['files'].get('pattern', {}).get('sha256'):
        return False
    return True

def update_stage(s):
    r = current(s)
    if r['kind'] == 'edit':
        s['stage'] = 'EDIT_CONFIRMED' if confirmed(r, 'edit') else 'EDIT_PENDING_CONFIRMATION'
    elif confirmed(r, 'png'):
        s['stage'] = 'PNG_CONFIRMED'
    elif 'pattern' in r['files']:
        s['stage'] = 'PNG_PENDING_CONFIRMATION'
    else:
        s['stage'] = 'PIXEL_CONFIRMED' if confirmed(r, 'pixel') else 'PIXEL_PENDING_CONFIRMATION'

def audit(project, event):
    with locked(project):
        with (Path(project) / 'events.jsonl').open('a') as f:
            f.write(json.dumps({'at': time.time(), **event}, ensure_ascii=False) + '\n')
