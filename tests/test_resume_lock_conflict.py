import fcntl
import os

from fastapi.testclient import TestClient
from server.app import app
from server import image_gen_app as routes


def test_resume_returns_conflict_when_existing_process_holds_run_lock(tmp_path,monkeypatch):
    root=tmp_path/'output'/'run';root.mkdir(parents=True)
    state=root/'state.txt';state.write_text('status=AUTHORING\n')
    monkeypatch.setenv('TOC_SERVER_AUTH_DISABLED','1')
    monkeypatch.setattr(routes,'ROOT',tmp_path)
    monkeypatch.setattr(routes,'_create_jobs',{})
    monkeypatch.setattr(routes,'_resume_tasks',{})
    descriptor=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
    try:
        fcntl.flock(descriptor,fcntl.LOCK_EX|fcntl.LOCK_NB)
        with TestClient(app,raise_server_exceptions=False) as client:
            response=client.post('/api/image-gen/runs/run/resume',json={'stop_target':'p680'})
        assert response.status_code==409, response.text
        assert 'すでに実行中' in response.json()['detail']
        assert routes._create_jobs=={}
        assert routes._resume_tasks=={}
        assert state.read_text()=='status=AUTHORING\n'
        # The original descriptor still owns the run lock; it was not reset.
        contender=os.open(root,os.O_RDONLY|os.O_DIRECTORY)
        try:
            try:
                fcntl.flock(contender,fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                pass
            else:
                raise AssertionError('original run lock was unexpectedly released')
        finally: os.close(contender)
    finally:
        fcntl.flock(descriptor,fcntl.LOCK_UN);os.close(descriptor)
