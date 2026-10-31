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

"""GUI regression tests for the AI chat panel and its Claude Code backend.

A fake claude script stands in for the CLI: it speaks the same stream-json protocol and
calls the bridge tools through the MCP config it is given, so the panel, the process and
the private bridge server are all exercised without signing in to anything.

To run tests:
    FreeCAD -t TestBridgeChat
"""

import json
import os
import shutil
import tempfile
import textwrap
import time
import unittest

import FreeCAD
import FreeCADGui
from PySide import QtCore, QtGui, QtWidgets

import Bridge
import BridgeChat
import BridgeChatPanel
from TestBridge import python_interpreter

FAKE_CLAUDE = textwrap.dedent("""
    import json, sys, urllib.request

    args = sys.argv[1:]
    with open(sys.argv[0] + ".args", "a", encoding="utf-8") as log:
        log.write(json.dumps(args) + "\\n")
    config = json.load(open(args[args.index("--mcp-config") + 1], encoding="utf-8"))
    server = config["mcpServers"]["othercad"]

    def out(message):
        sys.stdout.write(json.dumps(message) + "\\n")
        sys.stdout.flush()

    def delta(text):
        out({"type": "stream_event", "event": {"type": "content_block_delta",
             "delta": {"type": "text_delta", "text": text}}})

    def result(is_error=False, subtype="success"):
        out({"type": "result", "subtype": subtype, "is_error": is_error,
             "result": "", "session_id": "fake-session"})

    def call(name, arguments):
        body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
                "params": {"name": name, "arguments": arguments}}
        request = urllib.request.Request(server["url"], data=json.dumps(body).encode(),
                                         method="POST", headers=server["headers"])
        request.add_header("Content-Type", "application/json")
        with urllib.request.urlopen(request, timeout=30) as response:
            answer = json.loads(response.read())
        if "error" in answer:
            text = answer["error"]["message"]
            return {"isError": True, "content": [{"type": "text", "text": text}]}
        return answer["result"]

    out({"type": "system", "subtype": "init", "session_id": "fake-session"})
    for line in sys.stdin:
        message = json.loads(line)
        if message["type"] == "control_request":
            out({"type": "control_response", "response": {"subtype": "success",
                 "request_id": message["request_id"]}})
            result(True, "error_during_execution")
            continue
        text = message["message"]["content"]
        if text == "crash":
            sys.stderr.write("boom\\n")
            sys.exit(3)
        elif text == "slow":
            delta("Thinking")
        elif text.startswith("tool "):
            name = text.split()[1]
            out({"type": "assistant", "message": {"content": [{"type": "tool_use",
                 "id": "t1", "name": "mcp__othercad__" + name, "input": {}}]}})
            answer = call(name, {})
            out({"type": "user", "message": {"content": [{"type": "tool_result",
                 "tool_use_id": "t1", "is_error": answer["isError"],
                 "content": answer["content"]}]}})
            delta("Done.")
            result()
        else:
            delta("Hel")
            delta("lo **there**")
            result()
    """)


def key_press(key, modifiers):
    return QtGui.QKeyEvent(QtCore.QEvent.KeyPress, key, modifiers)


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


class ChatCase(unittest.TestCase):
    """A chat panel whose Claude is the fake script."""

    def setUp(self):
        if python_interpreter() is None:
            raise unittest.SkipTest("No Python interpreter to run the fake CLI with")
        self.params = Bridge.params()
        self.saved = {
            "ChatModel": self.params.GetString("ChatModel", ""),
            "ClaudePath": self.params.GetString("ClaudePath", ""),
            "ReadOnly": self.params.GetBool("ReadOnly", False),
        }
        self.params.SetString("ChatModel", "")
        self.params.SetBool("ReadOnly", False)
        self.dir = tempfile.mkdtemp(prefix="othercad-chat-test-")
        self.script = os.path.join(self.dir, "claude.py")
        with open(self.script, "w", encoding="utf-8") as stream:
            stream.write(FAKE_CLAUDE)
        self.doc = FreeCAD.newDocument("TestBridgeChat")
        self.panel = BridgeChatPanel.ChatPanel(
            providerFactory=lambda parent: BridgeChat.ClaudeCodeProvider(
                parent, command=[python_interpreter(), self.script]
            )
        )
        self.panel.resize(400, 600)
        self.panel.show()

    def tearDown(self):
        self.panel.shutdown()
        self.panel.deleteLater()
        FreeCAD.closeDocument(self.doc.Name)
        self.params.SetString("ChatModel", self.saved["ChatModel"])
        self.params.SetString("ClaudePath", self.saved["ClaudePath"])
        self.params.SetBool("ReadOnly", self.saved["ReadOnly"])
        if not self.saved["ClaudePath"]:
            self.params.RemString("ClaudePath")
        shutil.rmtree(self.dir, ignore_errors=True)

    @property
    def provider(self):
        return self.panel.provider

    def say(self, message, wait=True):
        self.panel.input.setPlainText(message)
        self.panel.sendOrStop()
        if wait:
            # send() goes busy at once; a warm process can answer within one event pump
            self.assertTrue(self.provider.busy)
            wait_until(lambda: not self.provider.busy)
        self.panel.render()

    def calls(self):
        with open(self.script + ".args", encoding="utf-8") as log:
            return [json.loads(line) for line in log]

    def kinds(self):
        return [entry["kind"] for entry in self.panel.entries]


class TestChatPanel(ChatCase):
    def test_a_reply_streams_into_the_transcript(self):
        self.say("hello")
        self.assertEqual(self.kinds(), ["user", "assistant"])
        self.assertEqual(self.panel.entries[1]["text"], "Hello **there**")
        text = self.panel.transcript.toPlainText()
        self.assertIn("hello", text)
        self.assertIn("Hello there", text)
        self.assertEqual(self.panel.sendButton.text(), "Send")
        self.assertEqual(self.panel.input.toPlainText(), "")

    def test_enter_sends_and_shift_enter_starts_a_new_line(self):
        self.panel.input.setFocus()
        self.panel.input.setPlainText("hel")
        self.panel.input.moveCursor(QtGui.QTextCursor.End)
        QtCore.QCoreApplication.sendEvent(
            self.panel.input, key_press(QtCore.Qt.Key_Return, QtCore.Qt.ShiftModifier)
        )
        self.assertEqual(self.panel.input.toPlainText(), "hel\n")
        self.panel.input.setPlainText("hello")
        QtCore.QCoreApplication.sendEvent(
            self.panel.input, key_press(QtCore.Qt.Key_Return, QtCore.Qt.NoModifier)
        )
        wait_until(lambda: not self.provider.busy and "assistant" in self.kinds())
        self.assertEqual(self.panel.entries[0]["text"], "hello")

    def test_a_tool_call_runs_through_the_private_bridge(self):
        self.say("tool get_document")
        tool = [entry for entry in self.panel.entries if entry["kind"] == "tool"][0]
        self.assertEqual(tool["name"], "get_document")
        isError, summary = tool["result"]
        self.assertFalse(isError, summary)
        self.assertIn("TestBridgeChat", summary)
        self.assertIn("✓", self.panel.transcript.toPlainText())
        self.assertFalse(Bridge.isRunning(), "The chat must not switch on the shared bridge")

    def test_a_failed_tool_call_is_marked(self):
        self.say("tool no_such_tool")
        tool = [entry for entry in self.panel.entries if entry["kind"] == "tool"][0]
        self.assertTrue(tool["result"][0])
        self.assertIn("✗", self.panel.transcript.toPlainText())

    def test_the_cli_gets_only_the_bridge_tools_and_none_of_the_users_settings(self):
        self.say("hello")
        args = self.calls()[0]
        self.assertEqual(args[args.index("--tools") + 1], "")
        self.assertEqual(args[args.index("--setting-sources") + 1], "")
        self.assertEqual(args[args.index("--permission-mode") + 1], "dontAsk")
        self.assertEqual(args[args.index("--allowedTools") + 1], "mcp__othercad")
        self.assertIn("--strict-mcp-config", args)
        self.assertNotIn("--model", args)
        with open(args[args.index("--mcp-config") + 1], encoding="utf-8") as stream:
            server = json.load(stream)["mcpServers"]["othercad"]
        self.assertTrue(server["url"].startswith("http://127.0.0.1:"))
        self.assertNotEqual(server["url"], f"http://127.0.0.1:{Bridge.DEFAULT_PORT}/mcp")
        self.assertRegex(server["headers"]["Authorization"], r"^Bearer \S{16,}$")

    def test_a_conversation_keeps_one_process(self):
        self.say("hello")
        # The transcript first, so a CLI that quit shows its error in the failure
        self.assertEqual(self.kinds(), ["user", "assistant"], self.panel.entries)
        process = self.provider.process
        self.assertIsNotNone(process)
        self.say("hello")
        self.assertEqual(self.kinds(), ["user", "assistant"] * 2, self.panel.entries)
        self.assertIs(self.provider.process, process)
        self.assertEqual(len(self.calls()), 1)

    def test_a_new_model_carries_the_conversation_over(self):
        self.say("hello")
        self.panel.modelBox.setCurrentIndex(self.panel.modelBox.findData("haiku"))
        self.panel._modelChosen(self.panel.modelBox.currentIndex())
        self.say("hello")
        args = self.calls()[-1]
        self.assertEqual(args[args.index("--model") + 1], "haiku")
        self.assertEqual(args[args.index("--resume") + 1], "fake-session")
        self.assertEqual(self.params.GetString("ChatModel", ""), "haiku")

    def test_a_new_chat_forgets_the_conversation(self):
        self.say("hello")
        self.panel.newChat()
        self.assertEqual(self.panel.entries, [])
        self.assertIsNone(self.provider.process)
        self.say("hello")
        self.assertNotIn("--resume", self.calls()[-1])

    def test_stop_interrupts_the_reply_without_an_error(self):
        self.say("slow", wait=False)
        wait_until(lambda: "assistant" in self.kinds())
        self.assertEqual(self.panel.sendButton.text(), "Stop")
        self.panel.sendOrStop()
        wait_until(lambda: not self.provider.busy)
        self.panel.render()
        self.assertEqual(self.kinds(), ["user", "assistant", "note"])
        self.assertIn("Stopped.", self.panel.transcript.toPlainText())
        self.say("hello")
        self.assertEqual(self.kinds()[-1], "assistant")

    def test_a_crashed_cli_is_reported_with_its_output(self):
        self.say("crash", wait=False)
        wait_until(lambda: "error" in self.kinds())
        wait_until(lambda: not self.provider.busy)
        error = self.panel.entries[-1]["text"]
        self.assertIn("exit code 3", error)
        self.assertIn("boom", error)
        self.say("hello")
        self.assertEqual(self.kinds()[-1], "assistant")

    def test_the_private_bridge_follows_the_read_only_preference(self):
        self.params.SetBool("ReadOnly", True)
        documents = set(FreeCAD.listDocuments())
        self.say("tool new_document")
        tool = [entry for entry in self.panel.entries if entry["kind"] == "tool"][0]
        self.assertTrue(tool["result"][0], "A read-only chat must not change anything")
        self.assertEqual(set(FreeCAD.listDocuments()), documents)


class TestChatWithoutClaude(unittest.TestCase):
    def setUp(self):
        self.params = Bridge.params()
        self.saved = self.params.GetString("ClaudePath", "")
        self.params.SetString("ClaudePath", os.path.join(tempfile.gettempdir(), "no-claude.exe"))
        self.panel = BridgeChatPanel.ChatPanel()

    def tearDown(self):
        self.panel.shutdown()
        self.panel.deleteLater()
        if self.saved:
            self.params.SetString("ClaudePath", self.saved)
        else:
            self.params.RemString("ClaudePath")

    def test_a_missing_cli_explains_how_to_install_it(self):
        self.panel.input.setPlainText("hello")
        self.panel.sendOrStop()
        self.panel.render()
        self.assertEqual(self.panel.entries[-1]["kind"], "error")
        self.assertIn("claude.com/claude-code", self.panel.entries[-1]["text"])
        self.assertFalse(self.panel.provider.busy)
        self.assertEqual(self.panel.sendButton.text(), "Send")


class TestChatCommand(unittest.TestCase):
    def test_the_tools_menu_toggles_the_dock(self):
        mainWindow = FreeCADGui.getMainWindow()
        actions = [a for a in mainWindow.findChildren(QtGui.QAction) if a.text() == "AI Chat"]
        self.assertTrue(actions, "AI Chat is not in the menus")
        dock = BridgeChatPanel.dock()
        wasVisible = dock.isVisible()
        try:
            FreeCADGui.runCommand("Bridge_Chat")
            self.assertNotEqual(dock.isVisible(), wasVisible)
            FreeCADGui.runCommand("Bridge_Chat")
            self.assertEqual(dock.isVisible(), wasVisible)
            self.assertEqual(dock.objectName(), "AIChat")
            self.assertIs(mainWindow.findChild(QtWidgets.QDockWidget, "AIChat"), dock)
        finally:
            dock.setVisible(wasVisible)
