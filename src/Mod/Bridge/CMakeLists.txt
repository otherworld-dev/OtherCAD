# SPDX-License-Identifier: LGPL-2.1-or-later

SET(Bridge_SRCS
    Bridge.py
    BridgeServer.py
    BridgeTools.py
    InitGui.py
)
SOURCE_GROUP("" FILES ${Bridge_SRCS})

ADD_CUSTOM_TARGET(Bridge ALL
    SOURCES ${Bridge_SRCS}
)

fc_copy_sources(Bridge "${CMAKE_BINARY_DIR}/Mod/Bridge" ${Bridge_SRCS})

INSTALL(
    FILES
        ${Bridge_SRCS}
    DESTINATION
        Mod/Bridge
)
