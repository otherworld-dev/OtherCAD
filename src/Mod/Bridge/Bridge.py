# SPDX-License-Identifier: LGPL-2.1-or-later

"""The LLM bridge: an MCP server that lets an LLM client read, look at and change the model.

    import Bridge
    Bridge.start()      # listens on http://127.0.0.1:7720/mcp
    Bridge.stop()

Preferences live in BaseApp/Preferences/Mod/Bridge: Port (7720), Token (empty for none),
AutoStart (off), ReadOnly (off: clients may change the model) and AllowPython (on: the
run_python tool is offered).
"""

import FreeCAD

PARAMS = "User parameter:BaseApp/Preferences/Mod/Bridge"
DEFAULT_PORT = 7720

_server = None


def params():
    return FreeCAD.ParamGet(PARAMS)


def isRunning():
    return _server is not None


def url():
    return _server.url if _server else None


def start(port=None, token=None, read_only=None, allow_python=None):
    """Start listening on 127.0.0.1. Port 0 picks a free port. Returns the URL."""

    global _server
    if _server is not None:
        return _server.url
    import BridgeServer

    if port is None:
        port = params().GetInt("Port", DEFAULT_PORT)
    if token is None:
        token = params().GetString("Token", "")
    if read_only is None:
        read_only = params().GetBool("ReadOnly", False)
    if allow_python is None:
        allow_python = params().GetBool("AllowPython", True)
    server = BridgeServer.Server("127.0.0.1", port, token, read_only, allow_python)
    server.start()
    _server = server
    FreeCAD.Console.PrintMessage(f"LLM bridge listening on {server.url}\n")
    return server.url


def stop():
    global _server
    if _server is None:
        return
    server, _server = _server, None
    server.stop()
    FreeCAD.Console.PrintMessage("LLM bridge stopped\n")
