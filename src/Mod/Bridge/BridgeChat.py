# SPDX-License-Identifier: LGPL-2.1-or-later

"""The AI chat panel's backends: something that takes the user's messages and answers them,
using the bridge's tools to read and change the model.

A provider reports what happens as Qt signals, so the panel never blocks on it:

    text(str)                  part of the reply, as it streams in
    toolCall(str, object)      a bridge tool the model called, with its arguments
    toolResult(bool, str)      that call's outcome: whether it failed, and a short summary
    turnFinished(bool)         the reply is complete; True if the user stopped it
    failed(str)                something went wrong that the user should see
    busyChanged(bool)          whether a reply is being written

ClaudeCodeProvider runs the Claude Code CLI headless, so it uses the plan the user is
signed in to rather than an API key. It gets the bridge's tools, and nothing else, from a
private bridge server on a free port with its own token.

Other backends: BridgeChatApi (Claude with an API key).

Preferences live in BaseApp/Preferences/Mod/Bridge: ClaudePath (empty to search PATH and
~/.local/bin) and ChatModel (empty for the CLI's default). The private server follows the
bridge's ReadOnly and AllowPython settings.
"""

import json
import os
import secrets
import shutil
import sys
import tempfile
import weakref

import FreeCAD
from PySide import QtCore

import Bridge

SERVER_NAME = "othercad"
TOOL_PREFIX = f"mcp__{SERVER_NAME}__"
SUMMARY_LENGTH = 160
STDERR_KEPT = 4000

SYSTEM_PROMPT = (
    "You are the AI assistant in OtherCAD's chat panel, beside the 3D view the user is "
    f"watching. Work on their model with the {SERVER_NAME} tools; you have no shell or file "
    "access. Keep replies short: say what you changed or found, not how you went about it."
)

NOT_INSTALLED = (
    "Claude Code was not found. Install it from https://claude.com/claude-code and sign in "
    "once by running claude in a terminal, or set its path in the parameter editor under "
    "BaseApp/Preferences/Mod/Bridge/ClaudePath."
)


class Provider(QtCore.QObject):
    """What the panel needs from a backend. Subclasses emit the signals."""

    text = QtCore.Signal(str)
    toolCall = QtCore.Signal(str, object)
    toolResult = QtCore.Signal(bool, str)
    turnFinished = QtCore.Signal(bool)
    failed = QtCore.Signal(str)
    busyChanged = QtCore.Signal(bool)

    name = ""
    models = [("Default", "")]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.busy = False
        # Asked on the main thread before the AI runs Python; tests replace it
        self.approve = askToRunPython

    def send(self, message):
        raise NotImplementedError

    def stop(self):
        """Stop the reply being written, keeping the conversation."""

    def reset(self):
        """Forget the conversation."""

    def setModel(self, model):
        """Use this model from the next message on, keeping the conversation."""

    def shutdown(self):
        """Release everything; the provider is not used again."""

    def _setBusy(self, busy):
        if busy != self.busy:
            self.busy = busy
            self.busyChanged.emit(busy)


def askToRunPython(name, arguments, parent=None):
    """Show the user the code the AI wants to run and return whether they allow it."""

    from PySide import QtGui, QtWidgets

    if parent is None:
        try:
            import FreeCADGui

            parent = FreeCADGui.getMainWindow()
        except Exception:
            parent = None
    dialog = QtWidgets.QDialog(parent)
    dialog.setObjectName("AIChatRunPython")
    dialog.setWindowTitle("Run Python?")
    label = QtWidgets.QLabel(
        "The AI wants to run this Python inside OtherCAD. It runs with your account's access "
        "to your files and the network, so read it before you run it."
    )
    label.setWordWrap(True)
    code = QtWidgets.QPlainTextEdit(str(arguments.get("code", "")))
    code.setReadOnly(True)
    code.setFont(QtGui.QFontDatabase.systemFont(QtGui.QFontDatabase.FixedFont))
    code.setMinimumSize(520, 220)
    buttons = QtWidgets.QDialogButtonBox()
    run = buttons.addButton("Run", QtWidgets.QDialogButtonBox.AcceptRole)
    skip = buttons.addButton("Don't run", QtWidgets.QDialogButtonBox.RejectRole)
    run.setAutoDefault(False)
    skip.setDefault(True)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout = QtWidgets.QVBoxLayout(dialog)
    layout.addWidget(label)
    layout.addWidget(code, 1)
    layout.addWidget(buttons)
    allowed = dialog.exec() == QtWidgets.QDialog.Accepted
    dialog.deleteLater()
    return allowed


def _weakApprover(provider):
    """provider.approve, without the server keeping the provider alive.

    A strong reference would make a provider <-> server cycle, and Python frees cycles on
    whichever thread happens to collect, here an HTTP thread, where deleting the provider's
    Qt objects crashes the app.
    """

    ref = weakref.ref(provider)

    def approve(name, arguments):
        alive = ref()
        return bool(alive is not None and alive.approve(name, arguments))

    return approve


def findClaude():
    """The Claude Code executable, or None."""

    configured = Bridge.params().GetString("ClaudePath", "")
    if configured:
        return configured if os.path.isfile(configured) else None
    found = shutil.which("claude")
    if found:
        return found
    name = "claude.exe" if sys.platform == "win32" else "claude"
    local = os.path.join(os.path.expanduser("~"), ".local", "bin", name)
    return local if os.path.isfile(local) else None


def summarize(content):
    """A one-line summary of a tool result's content, which is text or a list of blocks."""

    if isinstance(content, list):
        parts = []
        for block in content:
            if block.get("type") == "text":
                parts.append(block.get("text", ""))
            elif block.get("type") == "image":
                parts.append("[image]")
        content = " ".join(parts)
    text = " ".join(str(content or "").split())
    if len(text) > SUMMARY_LENGTH:
        text = text[: SUMMARY_LENGTH - 1] + "…"
    return text


class ClaudeCodeProvider(Provider):
    """Claude through the Claude Code CLI in stream-json mode, one process per conversation.

    command overrides the executable, as a list, for tests.
    """

    name = "Claude (subscription)"
    models = [("Default", ""), ("Opus", "opus"), ("Sonnet", "sonnet"), ("Haiku", "haiku")]

    def __init__(self, parent=None, command=None):
        super().__init__(parent)
        self.command = command
        self.model = Bridge.params().GetString("ChatModel", "")
        self.process = None
        self.server = None
        self.configFile = None
        self.sessionId = None
        self.resumeId = None
        self.buffer = b""
        self.stderr = b""
        self.stopping = False
        self.quitting = False
        self.lastArguments = []

    # -- Provider ----------------------------------------------------------

    def send(self, message):
        if self.busy:
            return
        if self.process is None and not self._startProcess():
            return
        self.stopping = False
        self._setBusy(True)
        self._write({"type": "user", "message": {"role": "user", "content": message}})

    def stop(self):
        if self.busy and self.process is not None:
            self.stopping = True
            self._write(
                {
                    "type": "control_request",
                    "request_id": f"stop_{secrets.token_hex(4)}",
                    "request": {"subtype": "interrupt"},
                }
            )

    def reset(self):
        self._endProcess()
        self.sessionId = None
        self.resumeId = None

    def setModel(self, model):
        if model == self.model:
            return
        self.model = model
        Bridge.params().SetString("ChatModel", model)
        # The CLI takes the model at start, so carry the conversation into a new process
        if self.process is not None and not self.busy:
            resume = self.sessionId
            self._endProcess()
            self.resumeId = resume

    def shutdown(self):
        self._endProcess()
        if self.server is not None:
            self.server.stop()
            self.server = None
        if self.configFile:
            try:
                os.remove(self.configFile)
            except OSError:
                pass
            self.configFile = None

    # -- Process -----------------------------------------------------------

    def arguments(self):
        """The CLI's arguments, after the executable."""

        args = [
            "-p",
            "--input-format", "stream-json",
            "--output-format", "stream-json",
            "--verbose",
            "--include-partial-messages",
            # Only the bridge's tools: no shell, files or web, and nothing to ask about
            "--tools", "",
            "--mcp-config", self.configFile,
            "--strict-mcp-config",
            "--allowedTools", f"mcp__{SERVER_NAME}",
            "--permission-mode", "dontAsk",
            # The user's own settings, hooks and memory are for their coding sessions
            "--setting-sources", "",
            "--append-system-prompt", SYSTEM_PROMPT,
        ]  # fmt: skip
        if self.model:
            args += ["--model", self.model]
        if self.resumeId:
            args += ["--resume", self.resumeId]
        return args

    def _startServer(self):
        if self.server is not None:
            return
        import BridgeServer

        params = Bridge.params()
        token = secrets.token_urlsafe(24)
        self.server = BridgeServer.Server(
            "127.0.0.1",
            0,
            token,
            params.GetBool("ReadOnly", False),
            params.GetBool("AllowPython", True),
            approve=_weakApprover(self),
        )
        self.server.start()
        config = {
            "mcpServers": {
                SERVER_NAME: {
                    "type": "http",
                    "url": self.server.url,
                    "headers": {"Authorization": f"Bearer {token}"},
                }
            }
        }
        handle, self.configFile = tempfile.mkstemp(prefix="othercad-chat-", suffix=".json")
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(config, stream)

    def _startProcess(self):
        command = self.command or ([findClaude()] if findClaude() else None)
        if not command:
            self.failed.emit(NOT_INSTALLED)
            return False
        try:
            self._startServer()
        except OSError as error:
            self.failed.emit(f"The chat could not start its bridge: {error}")
            return False

        workDir = os.path.join(FreeCAD.getUserAppDataDir(), "AIChat")
        os.makedirs(workDir, exist_ok=True)
        self.buffer = b""
        self.stderr = b""
        self.quitting = False
        self.lastArguments = command[1:] + self.arguments()

        process = QtCore.QProcess(self)
        process.setWorkingDirectory(workDir)
        import BridgeServer

        # A tool call can wait on the user's approval, so give it longer than the default
        environment = QtCore.QProcessEnvironment.systemEnvironment()
        environment.insert(
            "MCP_TOOL_TIMEOUT", str(int((BridgeServer.APPROVAL_TIMEOUT + 60) * 1000))
        )
        process.setProcessEnvironment(environment)
        process.readyReadStandardOutput.connect(self._readOutput)
        process.readyReadStandardError.connect(self._readError)
        process.finished.connect(self._finished)
        process.errorOccurred.connect(self._processError)
        self.process = process
        process.start(command[0], self.lastArguments)
        if not process.waitForStarted(10000):
            self._endProcess()
            self.failed.emit(f"Claude Code did not start ({command[0]}).")
            return False
        self.resumeId = None
        return True

    def _endProcess(self):
        process = self.process
        if process is None:
            return
        self.quitting = True
        self.process = None
        process.closeWriteChannel()
        if not process.waitForFinished(3000):
            process.kill()
            process.waitForFinished(3000)
        process.deleteLater()
        self._setBusy(False)

    def _write(self, message):
        self.process.write((json.dumps(message) + "\n").encode("utf-8"))

    def _readOutput(self):
        process = self.sender() or self.process
        if process is not self.process:
            return
        self.buffer += bytes(process.readAllStandardOutput())
        *lines, self.buffer = self.buffer.split(b"\n")
        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                message = json.loads(line)
            except ValueError:
                FreeCAD.Console.PrintLog(f"AI chat: not JSON: {line[:200]!r}\n")
                continue
            self.handle(message)

    def _readError(self):
        process = self.sender() or self.process
        if process is self.process:
            self.stderr = (self.stderr + bytes(process.readAllStandardError()))[-STDERR_KEPT:]

    def _finished(self, exitCode, exitStatus=None):
        if self.sender() is not self.process or self.quitting:
            return
        self.process.deleteLater()
        self.process = None
        detail = self.stderr.decode("utf-8", "replace").strip()
        message = f"Claude Code stopped (exit code {exitCode})."
        if detail:
            message += "\n" + detail
        self.failed.emit(message)
        self._setBusy(False)

    def _processError(self, error):
        if error == QtCore.QProcess.FailedToStart and self.sender() is self.process:
            self.failed.emit(f"Claude Code could not be started: {self.process.errorString()}")

    # -- Stream ------------------------------------------------------------

    def handle(self, message):
        """Act on one line of the CLI's stream-json output."""

        kind = message.get("type")
        if kind == "system" and message.get("subtype") == "init":
            self.sessionId = message.get("session_id") or self.sessionId
        elif kind == "stream_event":
            event = message.get("event", {})
            delta = event.get("delta", {})
            if event.get("type") == "content_block_delta" and delta.get("type") == "text_delta":
                self.text.emit(delta.get("text", ""))
        elif kind == "assistant":
            for block in message.get("message", {}).get("content", []):
                if block.get("type") == "tool_use":
                    name = block.get("name", "")
                    if name.startswith(TOOL_PREFIX):
                        name = name[len(TOOL_PREFIX) :]
                    self.toolCall.emit(name, block.get("input", {}))
        elif kind == "user":
            content = message.get("message", {}).get("content", [])
            for block in content if isinstance(content, list) else []:
                if block.get("type") == "tool_result":
                    self.toolResult.emit(
                        bool(block.get("is_error")), summarize(block.get("content"))
                    )
        elif kind == "result":
            self.sessionId = message.get("session_id") or self.sessionId
            stopped = self.stopping
            self.stopping = False
            if message.get("is_error") and not stopped:
                errors = message.get("errors") or []
                detail = message.get("result") or "; ".join(map(str, errors))
                self.failed.emit(detail or f"Claude stopped: {message.get('subtype')}")
            self._setBusy(False)
            self.turnFinished.emit(stopped)


def providers():
    """Every backend the panel offers, in the order it lists them."""

    import BridgeChatApi

    return [ClaudeCodeProvider, BridgeChatApi.AnthropicApiProvider]
