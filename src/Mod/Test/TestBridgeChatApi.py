# SPDX-License-Identifier: LGPL-2.1-or-later
# SPDX-FileCopyrightText: 2026 FreeCAD contributors
# SPDX-FileNotice: Part of the FreeCAD project.

################################################################################
#                                                                              #
#   FreeCAD is free software: you can redistribute it and/or modify            #
#   it under the terms of the GNU Lesser General Public License as             #
#   published by the Free Software Foundation, either version 2.1              #
#   of the License, or (at your option) any later version.                     #
#                                                                              #
#   FreeCAD is distributed in the hope that it will be useful,                 #
#   but WITHOUT ANY WARRANTY; without even the implied warranty                #
#   of MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.                    #
#   See the GNU Lesser General Public License for more details.                #
#                                                                              #
#   You should have received a copy of the GNU Lesser General Public           #
#   License along with FreeCAD. If not, see https://www.gnu.org/licenses       #
#                                                                              #
################################################################################

"""GUI regression tests for the AI chat panel's API-key backend.

A fake Messages API on a local port answers with scripted server-sent events, so the real
Anthropic SDK, the tool loop and the panel are all exercised without a key or a network.

To run tests:
    FreeCAD -t TestBridgeChatApi
"""

import http.server
import json
import os
import threading
import time
import unittest

import FreeCAD
import FreeCADGui
from PySide import QtWidgets

import Bridge
import BridgeChatPanel

try:
    import anthropic  # noqa: F401

    import BridgeChatApi
except ImportError:
    BridgeChatApi = None


def wait_until(condition, timeout=20.0):
    app = QtWidgets.QApplication.instance()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        FreeCADGui.updateGui()
        app.processEvents()
        if condition():
            return
        time.sleep(0.02)
    raise AssertionError("Timed out waiting for the chat")


def message_start(model="claude-opus-5-5"):
    return {
        "type": "message_start",
        "message": {
            "id": "msg_fake",
            "type": "message",
            "role": "assistant",
            "model": model,
            "content": [],
            "stop_reason": None,
            "stop_sequence": None,
            "usage": {"input_tokens": 10, "output_tokens": 1},
        },
    }


def text_reply(*parts):
    events = [
        message_start(),
        {"type": "content_block_start", "index": 0, "content_block": {"type": "text", "text": ""}},
    ]
    for part in parts:
        events.append(
            {
                "type": "content_block_delta",
                "index": 0,
                "delta": {"type": "text_delta", "text": part},
            }
        )
    events += [
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": "end_turn", "stop_sequence": None},
            "usage": {"output_tokens": 5},
        },
        {"type": "message_stop"},
    ]
    return events


def tool_reply(name, arguments, call_id="toolu_1", stop_reason="tool_use"):
    return [
        message_start(),
        {
            "type": "content_block_start",
            "index": 0,
            "content_block": {"type": "tool_use", "id": call_id, "name": name, "input": {}},
        },
        {
            "type": "content_block_delta",
            "index": 0,
            "delta": {"type": "input_json_delta", "partial_json": json.dumps(arguments)},
        },
        {"type": "content_block_stop", "index": 0},
        {
            "type": "message_delta",
            "delta": {"stop_reason": stop_reason, "stop_sequence": None},
            "usage": {"output_tokens": 5},
        },
        {"type": "message_stop"},
    ]


SLOW = "slow"


class FakeMessagesApi:
    """POST /v1/messages answered from a script: each request takes the next reply."""

    def __init__(self):
        self.replies = []
        self.requests = []
        api = self

        class Handler(http.server.BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *args):
                pass

            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length))
                api.requests.append({"body": body, "headers": dict(self.headers)})
                reply = api.replies.pop(0) if api.replies else text_reply("(no script)")
                if isinstance(reply, tuple):  # (status, error body)
                    data = json.dumps(reply[1]).encode()
                    self.send_response(reply[0])
                    self.send_header("Content-Type", "application/json")
                    self.send_header("Content-Length", str(len(data)))
                    self.end_headers()
                    self.wfile.write(data)
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Connection", "close")
                self.end_headers()
                events = text_reply("Thinking")[:3] if reply == SLOW else reply
                for event in events:
                    self.wfile.write(
                        f"event: {event['type']}\ndata: {json.dumps(event)}\n\n".encode()
                    )
                    self.wfile.flush()
                if reply == SLOW:
                    # Keep the reply open, as a long answer would, until the client goes
                    deadline = time.monotonic() + 30
                    try:
                        while time.monotonic() < deadline:
                            time.sleep(0.1)
                            self.wfile.write(b'event: ping\ndata: {"type": "ping"}\n\n')
                            self.wfile.flush()
                    except OSError:
                        pass
                self.close_connection = True

        self.httpd = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.httpd.daemon_threads = True
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class ApiCase(unittest.TestCase):
    """A chat panel on the API-key backend, talking to the fake API."""

    key = "test-key"

    def setUp(self):
        if BridgeChatApi is None:
            raise unittest.SkipTest("The Anthropic SDK is not installed")
        self.params = Bridge.params()
        self.saved = {
            "ApiModel": self.params.GetString("ApiModel", ""),
            "AnthropicApiKey": self.params.GetString("AnthropicApiKey", ""),
            "ReadOnly": self.params.GetBool("ReadOnly", False),
            "env": os.environ.get("ANTHROPIC_API_KEY"),
        }
        self.params.SetString("ApiModel", "")
        self.params.SetBool("ReadOnly", False)
        self.api = FakeMessagesApi()
        self.doc = FreeCAD.newDocument("TestBridgeChatApi")
        self.panel = BridgeChatPanel.ChatPanel(
            providerFactory=lambda parent: BridgeChatApi.AnthropicApiProvider(
                parent, baseUrl=self.api.url, key=self.key
            )
        )
        self.panel.resize(400, 600)
        self.panel.show()

    def tearDown(self):
        self.panel.shutdown()
        self.panel.deleteLater()
        self.api.close()
        FreeCAD.closeDocument(self.doc.Name)
        self.params.SetString("ApiModel", self.saved["ApiModel"])
        if self.saved["ApiModel"] == "":
            self.params.RemString("ApiModel")
        if self.saved["AnthropicApiKey"]:
            self.params.SetString("AnthropicApiKey", self.saved["AnthropicApiKey"])
        else:
            self.params.RemString("AnthropicApiKey")
        self.params.SetBool("ReadOnly", self.saved["ReadOnly"])
        if self.saved["env"] is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = self.saved["env"]

    @property
    def provider(self):
        return self.panel.provider

    def say(self, message, wait=True):
        self.panel.input.setPlainText(message)
        self.panel.sendOrStop()
        if wait:
            wait_until(lambda: not self.provider.busy)
        self.panel.render()

    def kinds(self):
        return [entry["kind"] for entry in self.panel.entries]


class TestChatApi(ApiCase):
    def test_a_reply_streams_into_the_transcript(self):
        self.api.replies = [text_reply("Hel", "lo **there**")]
        self.say("hello")
        self.assertEqual(self.kinds(), ["user", "assistant"], self.panel.entries)
        self.assertEqual(self.panel.entries[1]["text"], "Hello **there**")
        self.assertIn("Hello there", self.panel.transcript.toPlainText())
        self.assertEqual(self.panel.sendButton.text(), "Send")

    def test_the_request_carries_the_key_the_tools_and_the_fallback(self):
        self.api.replies = [text_reply("ok")]
        self.say("hello")
        request = self.api.requests[0]
        body, headers = request["body"], {k.lower(): v for k, v in request["headers"].items()}
        # The SDK sends the API key as a bearer token
        self.assertEqual(headers["authorization"], "Bearer test-key")
        self.assertEqual(body["model"], "claude-opus-5-5")
        self.assertEqual(body["fallbacks"], "default")
        self.assertIn("server-side-fallback-2026-07-01", headers.get("anthropic-beta", ""))
        self.assertTrue(body["stream"])
        names = {tool["name"] for tool in body["tools"]}
        self.assertTrue({"get_document", "pad", "screenshot"} <= names, names)
        self.assertTrue(all(tool["eager_input_streaming"] for tool in body["tools"]))
        self.assertIn("OtherCAD", body["system"])
        self.assertEqual(body["messages"], [{"role": "user", "content": "hello"}])

    def test_a_tool_call_runs_in_process_and_its_result_goes_back(self):
        self.api.replies = [tool_reply("get_document", {}), text_reply("Done.")]
        self.say("what is open?")
        self.assertEqual(self.kinds(), ["user", "tool", "assistant"], self.panel.entries)
        tool = self.panel.entries[1]
        self.assertEqual(tool["name"], "get_document")
        self.assertFalse(tool["result"][0], tool["result"])
        follow_up = self.api.requests[1]["body"]["messages"]
        self.assertEqual([m["role"] for m in follow_up], ["user", "assistant", "user"])
        result = follow_up[2]["content"][0]
        self.assertEqual(result["type"], "tool_result")
        self.assertEqual(result["tool_use_id"], "toolu_1")
        self.assertIn("TestBridgeChatApi", result["content"][0]["text"])
        self.assertFalse(Bridge.isRunning(), "The API backend must not start the bridge")

    def test_tool_input_that_does_not_fit_the_schema_is_not_run(self):
        self.api.replies = [tool_reply("pad", {"length": "ten"}), text_reply("Sorry.")]
        self.say("pad it")
        tool = [e for e in self.panel.entries if e["kind"] == "tool"][0]
        self.assertTrue(tool["result"][0])
        result = self.api.requests[1]["body"]["messages"][2]["content"][0]
        self.assertTrue(result["is_error"])
        self.assertIn("INVALID_INPUT", result["content"])

    def test_a_cut_off_tool_call_is_never_run(self):
        self.api.replies = [tool_reply("new_document", {}, stop_reason="max_tokens")]
        documents = set(FreeCAD.listDocuments())
        self.say("make a document")
        self.assertEqual(set(FreeCAD.listDocuments()), documents)
        self.assertEqual(self.kinds()[-1], "error")
        self.assertIn("cut off", self.panel.entries[-1]["text"])

    def test_a_conversation_alternates_turns_and_carries_its_history(self):
        self.api.replies = [text_reply("one"), text_reply("two")]
        self.say("first")
        self.say("second")
        messages = self.api.requests[1]["body"]["messages"]
        self.assertEqual([m["role"] for m in messages], ["user", "assistant", "user"])
        self.assertEqual(messages[2]["content"], "second")

    def test_a_new_model_keeps_the_conversation(self):
        self.api.replies = [text_reply("one"), text_reply("two")]
        self.say("first")
        index = self.panel.modelBox.findData("claude-haiku-4-5")
        self.panel.modelBox.setCurrentIndex(index)
        self.panel._modelChosen(index)
        self.say("second")
        body = self.api.requests[1]["body"]
        self.assertEqual(body["model"], "claude-haiku-4-5")
        self.assertNotIn("fallbacks", body)
        self.assertEqual(len(body["messages"]), 3)
        self.assertEqual(self.params.GetString("ApiModel", ""), "claude-haiku-4-5")

    def test_stop_ends_the_reply_and_the_next_message_still_works(self):
        self.api.replies = [SLOW, text_reply("after")]
        self.say("go on", wait=False)
        wait_until(lambda: "assistant" in self.kinds())
        self.panel.sendOrStop()
        wait_until(lambda: not self.provider.busy, timeout=10)
        self.panel.render()
        self.assertEqual(self.kinds()[-1], "note", self.panel.entries)
        self.say("again")
        self.assertEqual(self.kinds()[-1], "assistant")
        roles = [m["role"] for m in self.api.requests[1]["body"]["messages"]]
        self.assertEqual(roles, ["user", "assistant", "user"])

    def test_a_rejected_key_says_so(self):
        self.api.replies = [
            (
                401,
                {
                    "type": "error",
                    "error": {"type": "authentication_error", "message": "invalid x-api-key"},
                },
            )
        ]
        self.say("hello")
        self.assertEqual(self.kinds()[-1], "error")
        self.assertIn("rejected the API key", self.panel.entries[-1]["text"])
        self.assertEqual(self.panel.sendButton.text(), "Send")

    def test_read_only_preferences_hide_and_block_the_tools_that_change_things(self):
        self.params.SetBool("ReadOnly", True)
        self.api.replies = [tool_reply("new_document", {}), text_reply("Fine.")]
        documents = set(FreeCAD.listDocuments())
        self.say("make a document")
        names = {tool["name"] for tool in self.api.requests[0]["body"]["tools"]}
        self.assertNotIn("new_document", names)
        self.assertIn("get_document", names)
        self.assertEqual(set(FreeCAD.listDocuments()), documents)
        tool = [e for e in self.panel.entries if e["kind"] == "tool"][0]
        self.assertTrue(tool["result"][0])


class TestChatApiKey(ApiCase):
    key = None  # the provider looks the key up itself

    def test_without_a_key_it_says_where_to_set_one(self):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        self.params.RemString("AnthropicApiKey")
        self.say("hello")
        self.assertEqual(self.kinds()[-1], "error")
        self.assertIn("Key…", self.panel.entries[-1]["text"])
        self.assertEqual(self.api.requests, [])

    def test_a_saved_key_is_used_and_the_environment_wins(self):
        os.environ.pop("ANTHROPIC_API_KEY", None)
        self.provider.setKey("saved-key")
        self.api.replies = [text_reply("one"), text_reply("two")]
        self.say("first")
        os.environ["ANTHROPIC_API_KEY"] = "env-key"
        self.say("second")
        keys = [
            {k.lower(): v for k, v in r["headers"].items()}["authorization"]
            for r in self.api.requests
        ]
        self.assertEqual(keys, ["Bearer saved-key", "Bearer env-key"])
        self.provider.setKey("")
        self.assertEqual(self.params.GetString("AnthropicApiKey", ""), "")

    def test_the_key_button_shows_only_for_backends_that_need_one(self):
        self.assertTrue(self.panel.keyButton.isVisible())


class TestChatProviderChoice(unittest.TestCase):
    def setUp(self):
        self.params = Bridge.params()
        self.saved = self.params.GetString("ChatProvider", "")

    def tearDown(self):
        if self.saved:
            self.params.SetString("ChatProvider", self.saved)
        else:
            self.params.RemString("ChatProvider")

    def test_the_backend_can_be_switched_and_is_remembered(self):
        self.params.SetString("ChatProvider", "ClaudeCodeProvider")
        panel = BridgeChatPanel.ChatPanel()
        try:
            names = [panel.providerBox.itemText(i) for i in range(panel.providerBox.count())]
            self.assertEqual(names, ["Claude (subscription)", "Claude (API key)"])
            self.assertTrue(panel.providerBox.isEnabled())
            self.assertFalse(panel.keyButton.isVisibleTo(panel))
            panel.providerBox.setCurrentIndex(1)
            panel._providerChosen(1)
            self.assertEqual(type(panel.provider).__name__, "AnthropicApiProvider")
            self.assertTrue(panel.keyButton.isVisibleTo(panel))
            self.assertEqual(self.params.GetString("ChatProvider", ""), "AnthropicApiProvider")
            self.assertEqual(panel.entries[-1]["kind"], "note")
        finally:
            panel.shutdown()
            panel.deleteLater()
        reopened = BridgeChatPanel.ChatPanel()
        try:
            self.assertEqual(reopened.providerBox.currentIndex(), 1)
        finally:
            reopened.shutdown()
            reopened.deleteLater()
