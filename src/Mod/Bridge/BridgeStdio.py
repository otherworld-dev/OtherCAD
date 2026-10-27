# SPDX-License-Identifier: LGPL-2.1-or-later

"""Relays MCP over stdio to the LLM bridge's HTTP endpoint, for clients that only start
stdio servers, such as LLM desktop apps:

    "othercad": {"command": "python", "args": ["<path>/BridgeStdio.py"]}

It needs nothing but Python's standard library and does not import FreeCAD. If OtherCAD
is not running, or its bridge is off, the client is told there are no tools yet; the
relay keeps checking, and tells the client the tool list has changed once the bridge
answers.

Environment: OTHERCAD_BRIDGE_URL (default http://127.0.0.1:7720/mcp) and
OTHERCAD_BRIDGE_TOKEN, if the bridge has a Token set.
"""

import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

URL = os.environ.get("OTHERCAD_BRIDGE_URL", "http://127.0.0.1:7720/mcp")
TOKEN = os.environ.get("OTHERCAD_BRIDGE_TOKEN", "")
TIMEOUT = 300.0
POLL_SECONDS = 3.0

NOT_RUNNING = (
    "OtherCAD is not answering. Open OtherCAD and switch on Tools > LLM Bridge "
    f"(it listens on {URL})."
)

_write_lock = threading.Lock()
_waiting_lock = threading.Lock()
_waiting = False


def write(message):
    data = json.dumps(message, separators=(",", ":"))
    with _write_lock:
        sys.stdout.write(data + "\n")
        sys.stdout.flush()


def post(message, timeout=TIMEOUT):
    """Send one message to the bridge; returns its answer, or None for a notification."""

    request = urllib.request.Request(URL, data=json.dumps(message).encode("utf-8"), method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("Accept", "application/json, text/event-stream")
    if TOKEN:
        request.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        body = response.read()
    return json.loads(body) if body else None


def bridge_up():
    try:
        post({"jsonrpc": "2.0", "id": "relay-ping", "method": "ping"}, timeout=5)
        return True
    except (OSError, ValueError):
        return False


def wait_for_bridge():
    """Poll until the bridge answers, then have the client list the tools again."""

    global _waiting
    with _waiting_lock:
        if _waiting:
            return
        _waiting = True

    def poll():
        global _waiting
        while not bridge_up():
            time.sleep(POLL_SECONDS)
        with _waiting_lock:
            _waiting = False
        write({"jsonrpc": "2.0", "method": "notifications/tools/list_changed"})

    threading.Thread(target=poll, daemon=True).start()


def offline_answer(message):
    """What to say for a request the bridge could not take."""

    msg_id = message.get("id")
    method = message.get("method")
    if method == "initialize":
        asked = (message.get("params") or {}).get("protocolVersion") or "2025-06-18"
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {
                "protocolVersion": asked,
                "capabilities": {"tools": {"listChanged": True}},
                "serverInfo": {"name": "othercad", "version": "relay"},
                "instructions": NOT_RUNNING,
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": []}}
    if method == "tools/call":
        return {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": {"content": [{"type": "text", "text": NOT_RUNNING}], "isError": True},
        }
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": -32000, "message": NOT_RUNNING}}


def handle(message):
    try:
        answer = post(message)
    except urllib.error.HTTPError as error:
        if message.get("id") is None:
            return
        text = f"The bridge refused the request (HTTP {error.code})"
        if error.code == 403:
            text += "; if it has a Token, set OTHERCAD_BRIDGE_TOKEN to match"
        write({"jsonrpc": "2.0", "id": message["id"], "error": {"code": -32000, "message": text}})
        return
    except (OSError, ValueError):
        if message.get("id") is not None:
            write(offline_answer(message))
            if message.get("method") in ("initialize", "tools/list", "tools/call"):
                wait_for_bridge()
        return
    if answer is None:
        return
    if message.get("method") == "initialize" and "result" in answer:
        # The relay can tell the client when tools appear, whatever the bridge says
        answer["result"].setdefault("capabilities", {})["tools"] = {"listChanged": True}
    write(answer)


def main():
    workers = []
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            write({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "Parse error"}})
            continue
        if not isinstance(message, dict):
            continue
        # Its own thread, so a long tool call does not hold up pings and cancellations
        worker = threading.Thread(target=handle, args=(message,), daemon=True)
        worker.start()
        workers = [w for w in workers if w.is_alive()] + [worker]
    # The client closed stdin: let answers already on their way go out
    for worker in workers:
        worker.join(TIMEOUT)


if __name__ == "__main__":
    main()
