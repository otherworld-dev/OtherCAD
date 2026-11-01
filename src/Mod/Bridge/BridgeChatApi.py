# SPDX-License-Identifier: LGPL-2.1-or-later

"""The AI chat panel's API-key backend: Claude through the Anthropic API, with the bridge's
tools run in-process rather than over MCP.

The key comes from ANTHROPIC_API_KEY, or else from BaseApp/Preferences/Mod/Bridge/
AnthropicApiKey (set with the panel's Key button). The model is ApiModel there.

Each reply runs on a worker thread so the window never waits on the network. Tool calls are
handed to the main thread, where the FreeCAD API has to run, and the worker waits for them.
The conversation is only ever appended to, so thinking blocks stay valid from turn to turn.
"""

import json
import os
import threading

from PySide import QtCore

import Bridge
import BridgeChat
import BridgeServer
import BridgeTools

MAX_TOKENS = 64000
FALLBACK_BETA = "server-side-fallback-2026-07-01"
# Models whose declined requests the API can retry on another model (fallbacks: "default")
FALLBACK_MODELS = {"claude-opus-5-5", "claude-sonnet-5-5"}
DEFAULT_MODEL = "claude-opus-5-5"
KEY_PARAM = "AnthropicApiKey"
MODEL_PARAM = "ApiModel"

NO_SDK = (
    "The Anthropic SDK is not installed in this OtherCAD. Use Claude (subscription) instead, "
    "or install the anthropic Python package."
)
NO_KEY = (
    "No Anthropic API key. Click Key… to paste one, or set ANTHROPIC_API_KEY before "
    "starting OtherCAD. Keys are made at https://platform.claude.com/settings/keys."
)
BAD_KEY = "Anthropic rejected the API key. Click Key… to replace it."


def apiKey():
    """The key to use: the environment's first, then the saved one; '' for none."""

    return os.environ.get("ANTHROPIC_API_KEY") or Bridge.params().GetString(KEY_PARAM, "")


def keyFromEnvironment():
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def toolDefinitions():
    """The bridge's tools, as the Messages API takes them, under the bridge's preferences."""

    params = Bridge.params()
    readOnly = params.GetBool("ReadOnly", False)
    allowPython = params.GetBool("AllowPython", True)
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "input_schema": tool.schema,
            "eager_input_streaming": True,
        }
        for tool in BridgeTools.TOOLS.values()
        if BridgeServer.offers(tool.name, readOnly, allowPython)
    ]


def invalidInput(schema, arguments):
    """Why streamed tool input does not fit its schema, or None.

    With eager input streaming the API no longer validates tool input, and a truncated or
    malformed input can still parse, so the required fields and their JSON types are checked
    before anything runs.
    """

    if not isinstance(arguments, dict):
        return "the input is not an object"
    for name in schema.get("required", []):
        if name not in arguments:
            return f"'{name}' is missing"
    types = {
        "string": str,
        "boolean": bool,
        "object": dict,
        "array": list,
        "number": (int, float),
        "integer": int,
    }
    for name, value in arguments.items():
        expected = schema.get("properties", {}).get(name, {}).get("type")
        wanted = types.get(expected) if isinstance(expected, str) else None
        if wanted is None:
            continue
        if isinstance(value, bool) and expected in ("number", "integer"):
            return f"'{name}' should be a {expected}"
        if not isinstance(value, wanted):
            return f"'{name}' should be a {expected}"
    return None


def toolResultContent(result):
    """An MCP tool result's content as tool_result content blocks."""

    blocks = []
    for item in result.get("content", []):
        if item.get("type") == "image":
            blocks.append(
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": item.get("mimeType", "image/png"),
                        "data": item.get("data", ""),
                    },
                }
            )
        else:
            blocks.append({"type": "text", "text": item.get("text", "")})
    return blocks


class AnthropicApiProvider(BridgeChat.Provider):
    """Claude through the Anthropic API with an API key.

    baseUrl and key override the endpoint and the key, for tests.
    """

    name = "Claude (API key)"
    models = [
        ("Opus 5.5", "claude-opus-5-5"),
        ("Sonnet 5.5", "claude-sonnet-5-5"),
        ("Haiku 4.5", "claude-haiku-4-5"),
    ]
    needsKey = True

    # Emitted on the worker thread, handled on the main thread
    _turnDone = QtCore.Signal(bool)

    def __init__(self, parent=None, baseUrl=None, key=None):
        super().__init__(parent)
        self.baseUrl = baseUrl
        self.key = key
        self.model = Bridge.params().GetString(MODEL_PARAM, "") or DEFAULT_MODEL
        self.history = []
        self.runner = BridgeServer.MainThreadRunner()
        self.stopping = threading.Event()
        self.worker = None
        self.stream = None
        self._turnDone.connect(self._finishTurn, QtCore.Qt.QueuedConnection)

    # -- Provider ----------------------------------------------------------

    def send(self, message):
        if self.busy:
            return
        try:
            import anthropic  # noqa: F401
        except ImportError:
            self.failed.emit(NO_SDK)
            return
        key = self.key or apiKey()
        if not key:
            self.failed.emit(NO_KEY)
            return
        self.history.append({"role": "user", "content": message})
        self.stopping.clear()
        self._setBusy(True)
        self.worker = threading.Thread(
            target=self._run, args=(key, self.model), name="OtherCAD AI chat", daemon=True
        )
        self.worker.start()

    def stop(self):
        if self.busy:
            self.stopping.set()
            # Closing the response ends a wait on the network at once
            stream = self.stream
            if stream is not None:
                try:
                    stream.close()
                except Exception:
                    pass

    def reset(self):
        self._join()
        self.history = []

    def setModel(self, model):
        # The conversation carries over: each request names its model
        self.model = model
        Bridge.params().SetString(MODEL_PARAM, model)

    def setKey(self, key):
        """Save the key in the preferences, or forget it when key is empty."""

        if key:
            Bridge.params().SetString(KEY_PARAM, key)
        else:
            Bridge.params().RemString(KEY_PARAM)

    def shutdown(self):
        self._join()

    def _join(self):
        if self.worker is not None and self.worker.is_alive():
            self.stopping.set()
            # The worker may be waiting on the main thread for a tool; let it finish
            while self.worker.is_alive():
                QtCore.QCoreApplication.processEvents()
                self.worker.join(0.02)
        self.worker = None

    def _finishTurn(self, stopped):
        self.worker = None
        self._setBusy(False)
        self.turnFinished.emit(stopped)

    # -- Worker ------------------------------------------------------------

    def _run(self, key, model):
        import anthropic

        stopped = False
        try:
            client = anthropic.Anthropic(api_key=key, base_url=self.baseUrl)
            stopped = self._converse(client, model)
        except anthropic.AuthenticationError:
            self.failed.emit(BAD_KEY)
        except anthropic.PermissionDeniedError as error:
            self.failed.emit(f"Anthropic refused the request: {_message(error)}")
        except anthropic.NotFoundError as error:
            self.failed.emit(f"Anthropic does not know model {model}: {_message(error)}")
        except anthropic.RateLimitError:
            self.failed.emit("Anthropic's rate limit was reached. Wait a moment and try again.")
        except anthropic.APIStatusError as error:
            self.failed.emit(f"Anthropic API error {error.status_code}: {_message(error)}")
        except anthropic.APIConnectionError as error:
            self.failed.emit(f"Could not reach Anthropic: {error}")
        except anthropic.AnthropicError as error:
            self.failed.emit(f"The Anthropic SDK failed: {error}")
        except Exception as error:  # never leave the panel busy
            self.failed.emit(f"The chat failed: {type(error).__name__}: {error}")
        finally:
            self.stream = None
            stopped = stopped or self.stopping.is_set()
            self._closeTurn("(Stopped by the user.)" if stopped else "(No reply.)")
            self._turnDone.emit(stopped)

    def _closeTurn(self, text):
        """End the history on an assistant turn, so the next message can follow it."""

        if self.history and self.history[-1]["role"] == "user":
            self.history.append({"role": "assistant", "content": [{"type": "text", "text": text}]})

    def _request(self, model):
        request = {
            "model": model,
            "max_tokens": MAX_TOKENS,
            "system": BridgeChat.SYSTEM_PROMPT + "\n\n" + BridgeServer.INSTRUCTIONS,
            "tools": toolDefinitions(),
            "messages": self.history,
            # Cache the tools, instructions and conversation so far between turns
            "cache_control": {"type": "ephemeral"},
        }
        if model in FALLBACK_MODELS:
            # A declined request is retried server-side on the model Anthropic recommends
            request["betas"] = [FALLBACK_BETA]
            request["fallbacks"] = "default"
        return request

    def _converse(self, client, model):
        """Run one reply to its end, tool calls included. True if the user stopped it."""

        while True:
            with client.beta.messages.stream(**self._request(model)) as stream:
                self.stream = stream
                for event in stream:
                    if self.stopping.is_set():
                        return True
                    if event.type == "text":
                        self.text.emit(event.text)
                response = stream.get_final_message()

            if response.stop_reason == "refusal":
                self.failed.emit("Claude declined to help with this request.")
                return False
            self.history.append({"role": "assistant", "content": response.content})

            calls = [block for block in response.content if block.type == "tool_use"]
            if not calls:
                if response.stop_reason == "max_tokens":
                    self.failed.emit("The reply was cut off at its length limit.")
                return False
            if response.stop_reason == "max_tokens":
                # A truncated tool input can still parse; never run it
                self.failed.emit("A tool call was cut off at the length limit and was not run.")
                self.history.append(
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "tool_result",
                                "tool_use_id": call.id,
                                "is_error": True,
                                "content": "Not run: the input was cut off.",
                            }
                            for call in calls
                        ],
                    }
                )
                return False

            results = []
            for call in calls:
                results.append(self._runTool(call))
                if self.stopping.is_set():
                    break
            # Every call needs a result, even the ones skipped by a stop
            answered = {result["tool_use_id"] for result in results}
            for call in calls:
                if call.id not in answered:
                    results.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": call.id,
                            "is_error": True,
                            "content": "Not run: the user stopped the reply.",
                        }
                    )
            self.history.append({"role": "user", "content": results})
            if self.stopping.is_set():
                return True

    def _runTool(self, call):
        arguments = call.input if isinstance(call.input, dict) else {}
        self.toolCall.emit(call.name, arguments)
        tool = BridgeTools.TOOLS.get(call.name)
        params = Bridge.params()
        if tool is None:
            problem = "unknown tool"
        elif not BridgeServer.offers(
            call.name, params.GetBool("ReadOnly", False), params.GetBool("AllowPython", True)
        ):
            problem = "not available: the bridge's preferences do not allow it"
        else:
            problem = invalidInput(tool.schema, call.input)
        if problem:
            text = f"INVALID_INPUT: {problem}: {json.dumps(call.input)}"
            self.toolResult.emit(True, BridgeChat.summarize(text))
            return {"type": "tool_result", "tool_use_id": call.id, "is_error": True, "content": text}

        result = BridgeServer.call_tool(self.runner, call.name, call.input)
        isError = bool(result.get("isError"))
        self.toolResult.emit(isError, BridgeChat.summarize(result.get("content")))
        return {
            "type": "tool_result",
            "tool_use_id": call.id,
            "is_error": isError,
            "content": toolResultContent(result),
        }


def _message(error):
    body = getattr(error, "body", None)
    if isinstance(body, dict):
        detail = body.get("error", {})
        if isinstance(detail, dict) and detail.get("message"):
            return detail["message"]
    return str(error)

