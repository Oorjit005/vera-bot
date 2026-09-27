import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request

import pytest

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO_ROOT = os.path.normpath(os.path.join(_HERE, ".."))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

DATASET_DIR = os.environ.get("DATASET_DIR") or os.path.normpath(
    os.path.join(_HERE, "..", "..", "magicpin-ai-challenge", "expanded")
)

os.environ.setdefault("LLM_ENABLED", "0")
os.environ.setdefault("DATASET_DIR", DATASET_DIR)


def _free_port() -> int:
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


class HTTPClient:
    def __init__(self, base_url: str):
        self.base_url = base_url

    def _request(self, method: str, path: str, data: bytes = None):
        headers = {"Connection": "close"}
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base_url + path, data=data, headers=headers, method=method)
        last_err = None
        for attempt in range(6):
            try:
                with urllib.request.urlopen(req, timeout=10) as resp:
                    raw = resp.read().decode("utf-8")
                    return resp.status, (json.loads(raw) if raw else {})
            except urllib.error.HTTPError as e:
                raw = e.read().decode("utf-8")
                return e.code, (json.loads(raw) if raw else {})
            except (ConnectionError, OSError) as e:
                # Windows loopback sockets occasionally get reset by local AV/firewall
                # hooks under rapid connect/disconnect; retry with backoff.
                last_err = e
                time.sleep(0.05 * (2 ** attempt))
        raise last_err

    def get(self, path: str):
        return self._request("GET", path)

    def post(self, path: str, body: dict = None):
        data = json.dumps(body if body is not None else {}).encode("utf-8")
        return self._request("POST", path, data)

    def post_raw(self, path: str, raw_bytes: bytes):
        return self._request("POST", path, raw_bytes)


@pytest.fixture(scope="session")
def base_url():
    import uvicorn
    from app.main import app

    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    url = f"http://127.0.0.1:{port}"
    deadline = time.time() + 15
    last_err = None
    while time.time() < deadline:
        try:
            urllib.request.urlopen(url + "/v1/healthz", timeout=1)
            break
        except Exception as e:
            last_err = e
            time.sleep(0.1)
    else:
        raise RuntimeError(f"server did not start: {last_err}")

    yield url

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def client(base_url):
    c = HTTPClient(base_url)
    c.post("/v1/teardown")
    yield c
    c.post("/v1/teardown")


@pytest.fixture(scope="session")
def dataset_dir():
    return DATASET_DIR
