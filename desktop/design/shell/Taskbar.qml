// Zaod shell taskbar: a floating, centred panel with pinned apps and status.
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../qml"

Rectangle {
    id: taskbar

    property var pinned: []
    property var running: []
    property int activeIndex: -1
    property bool liteMode: false

    signal appActivated(string appId)
    signal startRequested()
    signal quickSettingsRequested()
    signal notificationsRequested()

    implicitWidth: layout.implicitWidth + ZaodTheme.space4 * 2
    implicitHeight: liteMode ? 40 : 44
    radius: ZaodTheme.radiusLg
    color: Qt.rgba(ZaodTheme.surface.r, ZaodTheme.surface.g, ZaodTheme.surface.b, 0.92)
    border.width: ZaodTheme.hairline
    border.color: ZaodTheme.border

    RowLayout {
        id: layout
        anchors.centerIn: parent
        spacing: ZaodTheme.space1

        ZaodButton {
            variant: ZaodButton.Variant.Quiet
            label: "\u25A6"
            size: taskbar.implicitHeight - ZaodTheme.space2
            onClicked: taskbar.startRequested()
            Accessible.name: qsTr("Open the Start menu")
        }

        Repeater {
            model: taskbar.pinned
            delegate: Item {
                width: taskbar.implicitHeight - ZaodTheme.space2
                height: width

                Rectangle {
                    anchors.fill: parent
                    radius: ZaodTheme.radiusMd
                    color: area.containsMouse || taskbar.activeIndex === index
                        ? ZaodTheme.surfaceAlt : "transparent"
                    Behavior on color {
                        ColorAnimation { duration: ZaodTheme.motionFast; easing.type: Easing.OutCubic }
                    }
                }

                Text {
                    anchors.centerIn: parent
                    text: modelData.icon || "\u25A3"
                    color: ZaodTheme.textPrimary
                    font.pixelSize: 18
                }

                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottomMargin: 2
                    width: taskbar.running.indexOf(modelData.id) >= 0 ? ZaodTheme.space1 * 4 : 0
                    height: 2
                    radius: 1
                    color: ZaodTheme.accent
                    Behavior on width { NumberAnimation { duration: ZaodTheme.motionFast } }
                }

                MouseArea {
                    id: area
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        taskbar.activeIndex = index
                        taskbar.appActivated(modelData.id)
                    }
                }
            }
        }

        Rectangle {
            width: ZaodTheme.hairline
            height: taskbar.implicitHeight / 2
            color: ZaodTheme.border
        }

        ZaodButton {
            variant: ZaodButton.Variant.Quiet
            label: "\u25A4"
            size: taskbar.implicitHeight - ZaodTheme.space2
            onClicked: taskbar.notificationsRequested()
            Accessible.name: qsTr("Notifications and calendar")
        }

        ZaodButton {
            variant: ZaodButton.Variant.Quiet
            label: clock.text
            size: taskbar.implicitHeight - ZaodTheme.space2
            onClicked: taskbar.notificationsRequested()
            Accessible.name: qsTr("Date and time")
        }

        ZaodButton {
            variant: ZaodButton.Variant.Quiet
            label: "\u2699"
            size: taskbar.implicitHeight - ZaodTheme.space2
            onClicked: taskbar.quickSettingsRequested()
            Accessible.name: qsTr("Quick settings")
        }
    }

    Timer {
        id: clockTimer
        interval: 30000
        running: true
        repeat: true
        onTriggered: clock.text = Qt.formatTime(new Date(), "HH:mm")
    }

    Text {
        id: clock
        visible: false
        text: Qt.formatTime(new Date(), "HH:mm")
        onTextChanged: clockTimer.running = true
    }
}
