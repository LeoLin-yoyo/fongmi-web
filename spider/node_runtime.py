"""Node.js Spider Engine Wrapper"""
import json
import os
import subprocess
import threading
import time
import urllib.request

from spider.net import ensure_http_url

_NODE_PROC = None
_LOCK = threading.Lock()


def _ensure_node():
    global _NODE_PROC
    with _LOCK:
        if _NODE_PROC is not None and _NODE_PROC.poll() is None:
            return True
        script = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "spider", "node_engine.cjs")
        if not os.path.exists(script):
            return False
        try:
            _NODE_PROC = subprocess.Popen(
                ["node", script],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,
            )
            for _ in range(20):
                try:
                    urllib.request.urlopen("http://127.0.0.1:19999/", timeout=1)
                    break
                except Exception:
                    time.sleep(0.2)
            return True
        except Exception:
            return False


def _post(payload):
    data = json.dumps(payload).encode()
    node_url = ensure_http_url("http://127.0.0.1:19999/", allow_private=True)
    req = urllib.request.Request(node_url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=35) as resp:
            return json.loads(resp.read())
    except Exception as e:
        return {"ok": False, "error": str(e)}


class NodeSpider:
    def __init__(self, key, api_url, ext=""):
        self.key = key
        self.api_url = api_url
        self.ext = ext
        self._loaded = False

    def load(self):
        if self._loaded:
            return True
        r = _post({"action": "load", "payload": {"apiUrl": self.api_url, "key": self.key}})
        self._loaded = r.get("ok", False)
        return self._loaded

    def call(self, method, *args):
        if not self._loaded and not self.load():
            return {}
        r = _post({"action": "call", "payload": {"key": self.key, "method": method, "args": list(args)}})
        if r.get("ok"):
            return r.get("result", {})
        return {}

    def destroy(self):
        _post({"action": "destroy", "payload": {"key": self.key}})


def ensure_engine():
    return _ensure_node()
