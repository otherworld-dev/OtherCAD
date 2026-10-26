# SPDX-License-Identifier: LGPL-2.1-or-later

"""An MCP server (streamable HTTP, JSON responses) that serves the bridge's tools.

HTTP is handled on worker threads, but the FreeCAD API is not thread-safe, so every
tool call is handed to the Qt main thread and the worker waits for its answer.
"""

import base64
import http.server
import json
import threading
import traceback

import FreeCAD
from PySide import QtCore

import BridgeTools

PROTOCOL_VERSIONS = ("2025-06-18", "2025-03-26", "2024-11-05")
CALL_TIMEOUT = 120.0
MAX_BODY = 4 * 1024 * 1024

INSTRUCTIONS = (
    "You are connected to a running OtherCAD session (a FreeCAD fork with a Fusion-style "
    "timeline). Read the model with get_document and get_timeline, inspect parts with "
    "get_shape, describe_faces and get_sketch, and look at it with screenshot. Lengths "
    "are in mm. get_selection shows what the user is pointing at."
)


class MainThreadRunner(QtCore.QObject):
    """Runs a function on the thread this object lives on and hands back its result."""

    request = QtCore.Signal(object)

    def __init__(self):
        super().__init__()
        self.request.connect(self._run, QtCore.Qt.QueuedConnection)

    def _run(self, job):
        func, done, outcome = job
        try:
            outcome["result"] = func()
        except BaseException as error:  # handed back to the waiting thread
            outcome["error"] = error
        finally:
            done.set()

    def call(self, func, timeout=CALL_TIMEOUT):
        if QtCore.QThread.currentThread() == self.thread():
            return func()
        done = threading.Event()
        outcome = {}
        self.request.emit((func, done, outcome))
        if not done.wait(timeout):
            raise TimeoutError(f"OtherCAD did not answer within {timeout:.0f} s")
        if "error" in outcome:
            raise outcome["error"]
        return outcome["result"]


def _rpc_error(msg_id, code, message):
    return {"jsonrpc": "2.0", "id": msg_id, "error": {"code": code, "message": message}}


def _tool_result(value):
    if isinstance(value, BridgeTools.Image):
        content = [
            {
                "type": "image",
                "data": base64.b64encode(value.data).decode("ascii"),
                "mimeType": value.mime_type,
            }
        ]
    else:
        content = [{"type": "text", "text": json.dumps(value, indent=1)}]
    return {"content": content, "isError": False}


def _tool_error(text):
    return {"content": [{"type": "text", "text": text}], "isError": True}


class Server:
    def __init__(self, host="127.0.0.1", port=7720, token=""):
        self.host = host
        self.token = token
        self.runner = MainThreadRunner()
        self.httpd = http.server.ThreadingHTTPServer((host, port), self._handler_class())
        self.httpd.daemon_threads = True
        self.port = self.httpd.server_address[1]
        self.thread = None

    @property
    def url(self):
        return f"http://{self.host}:{self.port}/mcp"

    def start(self):
        self.thread = threading.Thread(
            target=self.httpd.serve_forever, name="OtherCAD bridge", daemon=True
        )
        self.thread.start()

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        if self.thread:
            self.thread.join(5)

    # -- MCP -----------------------------------------------------------------

    def handle(self, message):
        """Answer one JSON-RPC message, or return None for a notification."""

        if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
            return _rpc_error(None, -32600, "Not a JSON-RPC 2.0 request")
        msg_id = message.get("id")
        method = message.get("method")
        params = message.get("params") or {}
        if msg_id is None:
            return None  # notifications/initialized and friends need no answer

        if method == "initialize":
            asked = params.get("protocolVersion")
            return {
                "jsonrpc": "2.0",
                "id": msg_id,
                "result": {
                    "protocolVersion": asked if asked in PROTOCOL_VERSIONS else PROTOCOL_VERSIONS[0],
                    "capabilities": {"tools": {"listChanged": False}},
                    "serverInfo": {"name": "othercad", "version": _app_version()},
                    "instructions": INSTRUCTIONS,
                },
            }
        if method == "ping":
            return {"jsonrpc": "2.0", "id": msg_id, "result": {}}
        if method == "tools/list":
            tools = [t.spec() for t in BridgeTools.TOOLS.values()]
            return {"jsonrpc": "2.0", "id": msg_id, "result": {"tools": tools}}
        if method == "tools/call":
            name = params.get("name")
            if name not in BridgeTools.TOOLS:
                return _rpc_error(msg_id, -32602, f"Unknown tool '{name}'")
            arguments = params.get("arguments") or {}
            return {"jsonrpc": "2.0", "id": msg_id, "result": self.call_tool(name, arguments)}
        return _rpc_error(msg_id, -32601, f"Unknown method '{method}'")

    def call_tool(self, name, arguments):
        FreeCAD.Console.PrintLog(f"Bridge: {name} {json.dumps(arguments)}\n")
        try:
            return _tool_result(self.runner.call(lambda: BridgeTools.call(name, arguments)))
        except BridgeTools.ToolError as error:
            return _tool_error(str(error))
        except Exception as error:
            text = "".join(traceback.format_exception_only(type(error), error)).strip()
            FreeCAD.Console.PrintWarning(f"Bridge: {name} failed: {text}\n")
            return _tool_error(text)

    # -- HTTP ----------------------------------------------------------------

    def allowed(self, headers):
        """Refuse requests a web page could forge: other hosts, other origins, no token."""

        hosts = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        if headers.get("Host") not in hosts:
            return False
        origin = headers.get("Origin")
        if origin and origin not in {f"http://{h}" for h in hosts}:
            return False
        if self.token and headers.get("Authorization") != f"Bearer {self.token}":
            return False
        return True

    def _handler_class(self):
        server = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, fmt, *args):
                pass

            def _reply(self, status, body=None):
                data = json.dumps(body).encode("utf-8") if body is not None else b""
                self.send_response(status)
                if body is not None:
                    self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def do_POST(self):
                if self.path.split("?")[0] != "/mcp":
                    return self._reply(404)
                if not server.allowed(self.headers):
                    return self._reply(403)
                length = int(self.headers.get("Content-Length") or 0)
                if length <= 0 or length > MAX_BODY:
                    return self._reply(413 if length > MAX_BODY else 400)
                try:
                    message = json.loads(self.rfile.read(length))
                except ValueError:
                    return self._reply(400, _rpc_error(None, -32700, "Parse error"))
                answer = server.handle(message)
                if answer is None:
                    return self._reply(202)
                self._reply(200, answer)

            def do_GET(self):
                # No server-initiated messages, so no SSE stream
                self._reply(405)

            def do_DELETE(self):
                self._reply(405)

        return Handler


def _app_version():
    try:
        major, minor, patch = FreeCAD.Version()[:3]
        return f"{major}.{minor}.{patch}"
    except Exception:
        return "0"
