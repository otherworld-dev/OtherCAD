# SPDX-License-Identifier: LGPL-2.1-or-later

"""The AI chat panel: a dock where the user talks to an AI that works on the open model
through the bridge's tools, without setting up an MCP client.

    import BridgeChatPanel
    BridgeChatPanel.show()
"""

import json

import FreeCADGui
from PySide import QtCore, QtWidgets

import Bridge
import BridgeChat
import BridgeGwyn

DOCK_NAME = "AIChat"
RENDER_DELAY_MS = 40
ARGUMENTS_SHOWN = 80

_dock = None


class ChatInput(QtWidgets.QPlainTextEdit):
    """Enter sends, Shift+Enter starts a new line."""

    submitted = QtCore.Signal()

    def keyPressEvent(self, event):
        if event.key() in (QtCore.Qt.Key_Return, QtCore.Qt.Key_Enter) and not (
            event.modifiers() & QtCore.Qt.ShiftModifier
        ):
            self.submitted.emit()
            return
        super().keyPressEvent(event)


class ChatPanel(QtWidgets.QWidget):
    """The transcript, the message box and the provider's controls.

    providerFactory makes the backend, for tests; otherwise the one chosen last
    (BaseApp/Preferences/Mod/Bridge/ChatProvider), or the first in providers().
    """

    def __init__(self, parent=None, providerFactory=None):
        super().__init__(parent)
        self.entries = []
        self.provider = None
        self.providerFactory = providerFactory

        self.providerBox = QtWidgets.QComboBox()
        self.modelBox = QtWidgets.QComboBox()
        self.keyButton = QtWidgets.QToolButton()
        self.keyButton.setText("Key\u2026")
        self.keyButton.setToolTip("Set the API key this backend uses")
        self.newButton = QtWidgets.QToolButton()
        self.newButton.setText("New chat")
        self.newButton.setToolTip("Start a new conversation")
        bar = QtWidgets.QHBoxLayout()
        bar.addWidget(self.providerBox, 1)
        bar.addWidget(self.modelBox)
        bar.addWidget(self.keyButton)
        bar.addWidget(self.newButton)

        self.transcript = QtWidgets.QTextBrowser()
        self.transcript.setOpenExternalLinks(True)
        self.transcript.setPlaceholderText(
            "Ask about the model or describe a change, such as “pad the sketch 10 mm "
            "and fillet the top edges by 1 mm”."
        )

        # Gwyn and a word on what the AI is doing, while a reply is on its way
        self.gwyn = BridgeGwyn.GwynWidget()
        self.statusLabel = QtWidgets.QLabel()
        self.status = QtWidgets.QWidget()
        statusRow = QtWidgets.QHBoxLayout(self.status)
        statusRow.setContentsMargins(0, 0, 0, 0)
        statusRow.addWidget(self.gwyn)
        statusRow.addWidget(self.statusLabel, 1)
        self.status.hide()

        self.input = ChatInput()
        self.input.setPlaceholderText("Message (Enter to send, Shift+Enter for a new line)")
        self.input.setTabChangesFocus(True)
        metrics = self.input.fontMetrics()
        self.input.setFixedHeight(metrics.lineSpacing() * 4 + 12)
        self.sendButton = QtWidgets.QPushButton("Send")

        row = QtWidgets.QHBoxLayout()
        row.addWidget(self.input, 1)
        row.addWidget(self.sendButton, 0, QtCore.Qt.AlignBottom)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.addLayout(bar)
        layout.addWidget(self.transcript, 1)
        layout.addWidget(self.status)
        layout.addLayout(row)

        self.renderTimer = QtCore.QTimer(self)
        self.renderTimer.setSingleShot(True)
        self.renderTimer.setInterval(RENDER_DELAY_MS)
        self.renderTimer.timeout.connect(self.render)

        self.providerClasses = BridgeChat.providers()
        for cls in self.providerClasses:
            self.providerBox.addItem(cls.name)
        chosen = Bridge.params().GetString("ChatProvider", "")
        names = [cls.__name__ for cls in self.providerClasses]
        self.providerBox.setCurrentIndex(names.index(chosen) if chosen in names else 0)
        self.providerBox.setEnabled(self.providerBox.count() > 1 and not providerFactory)
        self.input.submitted.connect(self.sendOrStop)
        self.sendButton.clicked.connect(self.sendOrStop)
        self.newButton.clicked.connect(self.newChat)
        self.keyButton.clicked.connect(self.askForKey)
        self.providerBox.activated.connect(self._providerChosen)
        self.modelBox.activated.connect(self._modelChosen)
        self._setProvider()

    # -- Provider ------------------------------------------------------------

    def _setProvider(self):
        if self.providerFactory:
            provider = self.providerFactory(self)
        else:
            provider = self.providerClasses[self.providerBox.currentIndex()](self)
        self.provider = provider
        provider.text.connect(self._text)
        provider.toolCall.connect(self._toolCall)
        provider.toolResult.connect(self._toolResult)
        provider.turnFinished.connect(self._turnFinished)
        provider.failed.connect(self._failed)
        provider.busyChanged.connect(self._busyChanged)

        self.modelBox.clear()
        for label, model in provider.models:
            self.modelBox.addItem(label, model)
        index = self.modelBox.findData(getattr(provider, "model", ""))
        self.modelBox.setCurrentIndex(max(index, 0))
        self.modelBox.setVisible(len(provider.models) > 1)
        self.keyButton.setVisible(getattr(provider, "needsKey", False))
        self._busyChanged(provider.busy)

    def _providerChosen(self, index):
        cls = self.providerClasses[index]
        if isinstance(self.provider, cls):
            return
        Bridge.params().SetString("ChatProvider", cls.__name__)
        self.provider.shutdown()
        self.provider.deleteLater()
        self._setProvider()
        self.entries = [{"kind": "note", "text": f"Now using {cls.name}. This is a new conversation."}]
        self.render()

    def askForKey(self):
        import BridgeChatApi

        note = ""
        if BridgeChatApi.keyFromEnvironment():
            note = "\n\nANTHROPIC_API_KEY is set, and it is used instead of a saved key."
        key, ok = QtWidgets.QInputDialog.getText(
            self,
            "Anthropic API key",
            "Paste your Anthropic API key. It is saved in OtherCAD's preferences; leave it "
            "empty to forget the saved key." + note,
            QtWidgets.QLineEdit.Password,
        )
        if ok:
            self.provider.setKey(key.strip())

    def _modelChosen(self, index):
        self.provider.setModel(self.modelBox.itemData(index))

    def sendOrStop(self):
        if self.provider.busy:
            self.provider.stop()
            return
        message = self.input.toPlainText().strip()
        if not message:
            return
        self.input.clear()
        self.entries.append({"kind": "user", "text": message})
        self.scheduleRender()
        self.provider.send(message)

    def newChat(self):
        self.provider.reset()
        self.entries = []
        self.render()
        self.input.setFocus()

    def shutdown(self):
        if self.provider:
            self.provider.shutdown()

    # -- Provider signals ----------------------------------------------------

    def _text(self, chunk):
        if not self.entries or self.entries[-1]["kind"] != "assistant":
            self.entries.append({"kind": "assistant", "text": ""})
        self.entries[-1]["text"] += chunk
        self.statusLabel.setText("Writing…")
        self.scheduleRender()

    def _toolCall(self, name, arguments):
        self.entries.append({"kind": "tool", "name": name, "arguments": arguments, "result": None})
        self.statusLabel.setText(f"Using {name}…")
        self.scheduleRender()

    def _toolResult(self, isError, summary):
        for entry in reversed(self.entries):
            if entry["kind"] == "tool" and entry["result"] is None:
                entry["result"] = (isError, summary)
                break
        self.statusLabel.setText("Thinking…")
        self.scheduleRender()

    def _turnFinished(self, stopped):
        if stopped:
            self.entries.append({"kind": "note", "text": "Stopped."})
        self.scheduleRender()

    def _failed(self, message):
        self.entries.append({"kind": "error", "text": message})
        self.scheduleRender()

    def _busyChanged(self, busy):
        self.sendButton.setText("Stop" if busy else "Send")
        self.sendButton.setToolTip("Stop the reply" if busy else "Send the message")
        self.modelBox.setEnabled(not busy)
        if busy:
            self.statusLabel.setText("Thinking…")
            self.status.show()
            self.gwyn.start()
        else:
            self.gwyn.stop()
            self.status.hide()

    # -- Transcript ----------------------------------------------------------

    def scheduleRender(self):
        if not self.renderTimer.isActive():
            self.renderTimer.start()

    def markdown(self):
        """The transcript as Markdown."""

        parts = []
        for entry in self.entries:
            kind = entry["kind"]
            if kind == "user":
                quoted = "\n".join("> " + line for line in entry["text"].splitlines())
                parts.append(f"**You**\n\n{quoted}")
            elif kind == "assistant":
                parts.append(entry["text"])
            elif kind == "tool":
                arguments = json.dumps(entry["arguments"], separators=(", ", ": "))
                if len(arguments) > ARGUMENTS_SHOWN:
                    arguments = arguments[: ARGUMENTS_SHOWN - 1] + "…"
                line = f"⚙ `{entry['name']}` `{arguments}`"
                if entry["result"] is None:
                    line += " …"
                elif entry["result"][0]:
                    line += f" ✗ *{_escape(entry['result'][1])}*"
                else:
                    line += " ✓"
                parts.append(line)
            elif kind == "note":
                parts.append(f"*{entry['text']}*")
            elif kind == "error":
                parts.append(f"**⚠ {_escape(entry['text'])}**")
        return "\n\n".join(parts)

    def render(self):
        self.renderTimer.stop()
        bar = self.transcript.verticalScrollBar()
        atEnd = bar.value() >= bar.maximum() - 4
        position = bar.value()
        self.transcript.setMarkdown(self.markdown())
        bar.setValue(bar.maximum() if atEnd else position)


def _escape(text):
    """Text shown as is inside Markdown emphasis."""

    for char in "\\`*_[]<>#":
        text = text.replace(char, "\\" + char)
    return " ".join(text.split())


class ChatDock(QtWidgets.QDockWidget):
    def __init__(self, parent=None, providerFactory=None):
        super().__init__("AI Chat", parent)
        self.setObjectName(DOCK_NAME)
        self.panel = ChatPanel(self, providerFactory)
        # Closing only hides it, so the conversation is still there when it is shown again
        self.setWidget(self.panel)


def dock():
    """The chat dock, made the first time it is asked for."""

    global _dock
    if _dock is None:
        mainWindow = FreeCADGui.getMainWindow()
        _dock = ChatDock(mainWindow)
        mainWindow.addDockWidget(QtCore.Qt.RightDockWidgetArea, _dock)
        QtWidgets.QApplication.instance().aboutToQuit.connect(_dock.panel.shutdown)
    return _dock


def show():
    chat = dock()
    chat.show()
    chat.raise_()
    chat.panel.input.setFocus()
    return chat


def toggle():
    chat = dock()
    if chat.isVisible():
        chat.hide()
    else:
        show()
