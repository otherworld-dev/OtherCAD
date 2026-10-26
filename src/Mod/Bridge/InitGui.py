# SPDX-License-Identifier: LGPL-2.1-or-later

"""Puts the LLM bridge's on/off switch in the Tools menu and starts it if asked to."""


class BridgeToggleCommand:
    def GetResources(self):
        return {
            "MenuText": "LLM Bridge",
            "ToolTip": "Let an LLM client read and look at the open "
            "model through MCP, on this computer only",
        }

    def IsActive(self):
        return True

    def Activated(self, checked=False):
        import Bridge

        if Bridge.isRunning():
            Bridge.stop()
        else:
            try:
                Bridge.start()
            except OSError as error:
                FreeCAD.Console.PrintError(f"LLM bridge could not start: {error}\n")


class BridgeMenuManipulator:
    def modifyMenuBar(self):
        return [{"insert": "Bridge_Toggle", "menuItem": "Std_DlgParameter", "after": ""}]


def _auto_start():
    import Bridge

    if Bridge.params().GetBool("AutoStart", False):
        try:
            Bridge.start()
        except OSError as error:
            FreeCAD.Console.PrintError(f"LLM bridge could not start: {error}\n")


Gui.addCommand("Bridge_Toggle", BridgeToggleCommand())
Gui.addWorkbenchManipulator(BridgeMenuManipulator())
_auto_start()
