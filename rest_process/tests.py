"""Tests for rest-process.

Unit tests use FastAPI's TestClient to exercise routes in-process (no
network, no thread). The integration test starts a real uvicorn server
in a background thread and drives it through process-bigraph's ``rest``
protocol — exactly the scenario the skipped ``test_rest_process`` in
process-bigraph guards against.
"""

import socket
import threading
import time
import uuid

import pytest
import uvicorn
from fastapi.testclient import TestClient

from process_bigraph import Composite, allocate_core

from rest_process.processes.grow import GrowProcess
from rest_process.server import start_server


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def core():
    core = allocate_core()
    core.register_link('Grow', GrowProcess)
    return core


@pytest.fixture
def client(core):
    """In-process TestClient — fast, no socket."""
    app = start_server(core)
    return TestClient(app)


# ---------------------------------------------------------------------------
# GrowProcess unit tests
# ---------------------------------------------------------------------------

def test_grow_process_update_returns_mass_delta(core):
    proc = GrowProcess({'rate': 0.1}, core=core)
    result = proc.update({'mass': 2.0}, interval=1.0)
    assert result == {'mass_delta': pytest.approx(0.2)}


def test_grow_process_update_scales_with_interval(core):
    proc = GrowProcess({'rate': 0.5}, core=core)
    short = proc.update({'mass': 1.0}, interval=0.1)
    long = proc.update({'mass': 1.0}, interval=2.0)
    assert long['mass_delta'] == pytest.approx(short['mass_delta'] * 20.0)


# ---------------------------------------------------------------------------
# Server route unit tests (TestClient — no network)
# ---------------------------------------------------------------------------

def test_list_types_returns_registered_types(client, core):
    resp = client.get('/list-types')
    assert resp.status_code == 200
    types = resp.json()
    assert isinstance(types, list)
    # Core registers a baseline of types on construction; spot-check a few.
    for expected in ('float', 'integer', 'string'):
        assert expected in types


def test_list_processes_includes_grow(client):
    resp = client.get('/list-processes')
    assert resp.status_code == 200
    procs = resp.json()
    assert 'Grow' in procs


def test_config_schema_for_known_process(client):
    resp = client.get('/process/Grow/config-schema')
    assert resp.status_code == 200
    schema = resp.json()
    assert 'rate' in schema


def test_config_schema_for_missing_process(client):
    resp = client.get('/process/DoesNotExist/config-schema')
    assert resp.status_code == 200
    # Current server: ``find_process_class`` falls back to Edge (whose
    # config_schema is empty), so the sentinel branch in
    # ``get_config_schema`` is unreachable. Documenting the *actual*
    # contract here. TODO: server should distinguish "missing" from
    # "registered with no config" by having find_process_class return
    # None on miss, then propagating a 404.
    assert resp.json() == {}


def test_initialize_then_inputs_outputs_then_update(client):
    init = client.post('/process/Grow/initialize', json={'rate': 0.1})
    assert init.status_code == 200
    process_id = init.json()
    # FastAPI serializes UUIDs as strings; verify it parses.
    uuid.UUID(process_id)

    inputs = client.get(f'/process/Grow/inputs/{process_id}')
    assert inputs.status_code == 200
    assert inputs.json() == {'mass': 'float'}

    outputs = client.get(f'/process/Grow/outputs/{process_id}')
    assert outputs.status_code == 200
    assert outputs.json() == {'mass_delta': 'float'}

    update = client.post(
        f'/process/Grow/update/{process_id}',
        json={'state': {'mass': 5.0}, 'interval': 2.0},
    )
    assert update.status_code == 200
    assert update.json() == {'mass_delta': pytest.approx(1.0)}


def test_end_removes_process(client):
    init = client.post('/process/Grow/initialize', json={'rate': 0.05})
    process_id = init.json()

    end = client.post(f'/process/Grow/end/{process_id}', json={})
    assert end.status_code == 200

    # Verify removal by attempting another end on the same id —
    # should fail because the entry was deleted. Using a fresh
    # TestClient avoids the closed-client state that the in-process
    # KeyError leaves behind in the original client.
    second_client = TestClient(client.app, raise_server_exceptions=False)
    second = second_client.post(f'/process/Grow/end/{process_id}', json={})
    assert second.status_code == 500


# ---------------------------------------------------------------------------
# Integration: real uvicorn + process-bigraph rest protocol
# ---------------------------------------------------------------------------

def _free_port() -> int:
    """Bind to port 0 to get an OS-assigned ephemeral port, then close."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


def _wait_for_port(host: str, port: int, timeout: float = 10.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection((host, port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.05)
    raise RuntimeError(f"server at {host}:{port} did not start within {timeout}s")


def test_rest_protocol_drives_grow_process(core):
    """Spin up a real server, run a Composite that talks to it via the
    rest protocol, and verify mass actually grows. This is the scenario
    process-bigraph's ``test_rest_process`` skips when no server is up."""
    port = _free_port()
    app = start_server(core)
    config = uvicorn.Config(app, host='127.0.0.1', port=port, log_level='warning')
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    try:
        _wait_for_port('127.0.0.1', port)

        state = {
            'mass': 1.0,
            'rest-process': {
                '_type': 'process',
                'address': {
                    'protocol': 'rest',
                    'data': {
                        'process': 'Grow',
                        'host': '127.0.0.1',
                        'port': port}},
                'config': {'rate': 0.005},
                'inputs': {'mass': ['mass']},
                # GrowProcess emits a port called mass_delta (not
                # mass), and float apply is additive — so each tick's
                # delta accumulates onto state['mass'].
                'outputs': {'mass_delta': ['mass']},
                'interval': 0.7}}

        composite = Composite({'state': state}, core=core)
        composite.run(11.111)
        assert composite.state['mass'] > 1.0
    finally:
        server.should_exit = True
        thread.join(timeout=5.0)
