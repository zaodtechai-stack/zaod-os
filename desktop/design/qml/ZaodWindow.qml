// Zaod Fluent window frame: title bar with drag area plus original window controls.
// Every metric comes from the token set; the title bar is the window's chrome
// height token, the controls sit on the minimum target size, and each control is
// reachable with Tab and activates with Space or Return.
import QtQuick 2.15
import QtQuick.Window 2.15

Window {
    id: window

    property string titleText: ""
    default property alias content: contentArea.data

    color: ZaodTheme.background
    flags: Qt.Window | Qt.FramelessWindowHint
    width: 960
    height: 640
    minimumWidth: ZaodTheme.windowMinWidth
    minimumHeight: ZaodTheme.windowMinHeight

    onActiveChanged: titleBar.active = active

    Rectangle {
        id: titleBar
        property bool active: true
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: ZaodTheme.windowChromeHeight
        color: active ? ZaodTheme.surface : ZaodTheme.surfaceAlt

        Rectangle {
            anchors.bottom: parent.bottom
            width: parent.width
            height: ZaodTheme.hairline
            color: ZaodTheme.border
        }

        Text {
            anchors.left: parent.left
            anchors.leftMargin: ZaodTheme.space4
            anchors.verticalCenter: parent.verticalCenter
            anchors.right: controls.left
            anchors.rightMargin: ZaodTheme.space2
            text: window.titleText
            elide: Text.ElideRight
            color: window.active ? ZaodTheme.textPrimary : ZaodTheme.textSecondary
            font.family: ZaodTheme.fontFamily
            font.pixelSize: ZaodTheme.scaled(ZaodTheme.typeBodySm.size)
            font.weight: Font.Medium
            Accessible.role: Accessible.Heading
            Accessible.name: window.titleText
        }

        MouseArea {
            anchors.fill: parent
            anchors.rightMargin: controls.width
            property point dragOrigin
            onPressed: dragOrigin = Qt.point(mouse.x, mouse.y)
            onPositionChanged: {
                window.x += mouse.x - dragOrigin.x
                window.y += mouse.y - dragOrigin.y
            }
        }

        Row {
            id: controls
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            height: parent.height

            Repeater {
                model: [
                    { glyph: "\u2013", action: "minimize", name: qsTr("Minimize") },
                    { glyph: "\u25A1", action: "maximize", name: qsTr("Maximize") },
                    { glyph: "\u2715", action: "close", name: qsTr("Close") }
                ]
                delegate: Item {
                    id: controlItem

                    // Half the chrome height, never below the pointer target floor.
                    readonly property int controlWidth: Math.max(
                        ZaodTheme.minPointerTarget, ZaodTheme.windowChromeHeight)
                    readonly property bool destructive: modelData.action === "close"
                    readonly property bool focused: navArea.activeFocus

                    width: controlWidth
                    height: parent.height
                    activeFocusOnTab: true

                    Accessible.role: Accessible.Button
                    Accessible.name: modelData.name
                    Accessible.onPressAction: activate()

                    function activate() {
                        if (modelData.action === "close") window.close()
                        else if (modelData.action === "minimize") window.showMinimized()
                        else if (window.visibility === Window.Maximized) window.showNormal()
                        else window.showMaximized()
                    }

                    Rectangle {
                        anchors.fill: parent
                        color: navArea.containsMouse || controlItem.focused
                            ? (controlItem.destructive ? ZaodTheme.danger : ZaodTheme.surfaceAlt)
                            : Qt.rgba(0, 0, 0, 0)
                    }

                    Text {
                        anchors.centerIn: parent
                        text: modelData.glyph
                        color: navArea.containsMouse || controlItem.focused
                            ? (controlItem.destructive ? ZaodTheme.onDanger : ZaodTheme.textPrimary)
                            : ZaodTheme.textSecondary
                        font.pixelSize: ZaodTheme.scaled(ZaodTheme.typeCaption.size)
                    }

                    // Focus is never carried by colour alone: a token-width ring
                    // is drawn inside the control so it survives any palette.
                    Rectangle {
                        anchors.fill: parent
                        anchors.margins: ZaodTheme.hairline
                        color: Qt.rgba(0, 0, 0, 0)
                        border.width: controlItem.focused ? ZaodTheme.focusRingWidth : 0
                        border.color: ZaodTheme.focusRing
                    }

                    Keys.onSpacePressed: activate()
                    Keys.onReturnPressed: activate()

                    MouseArea {
                        id: navArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: {
                            controlItem.forceActiveFocus()
                            controlItem.activate()
                        }
                    }
                }
            }
        }
    }

    Column {
        id: contentArea
        anchors.top: titleBar.bottom
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
    }
}
