// Zaod Fluent window frame: title bar with drag area plus original window controls.
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
    minimumWidth: 480
    minimumHeight: 320

    onActiveChanged: titleBar.active = active

    Rectangle {
        id: titleBar
        property bool active: true
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: ZaodTheme.space10
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
            text: window.titleText
            color: ZaodTheme.textPrimary
            font.family: ZaodTheme.fontFamily
            font.pixelSize: ZaodTheme.typeBodySm.size
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
                    { glyph: "\u2013", action: "minimize" },
                    { glyph: "\u25A1", action: "maximize" },
                    { glyph: "\u2715", action: "close" }
                ]
                delegate: Rectangle {
                    width: ZaodTheme.space12
                    height: parent.height
                    color: area.containsMouse
                        ? (modelData.action === "close" ? ZaodTheme.danger : ZaodTheme.surfaceAlt)
                        : "transparent"

                    Text {
                        anchors.centerIn: parent
                        text: modelData.glyph
                        color: area.containsMouse && modelData.action === "close"
                            ? ZaodTheme.onDanger : ZaodTheme.textSecondary
                        font.pixelSize: 11
                    }

                    MouseArea {
                        id: area
                        anchors.fill: parent
                        hoverEnabled: true
                        onClicked: {
                            if (modelData.action === "close") window.close()
                            else if (modelData.action === "minimize") window.showMinimized()
                            else if (window.visibility === Window.Maximized) window.showNormal()
                            else window.showMaximized()
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
