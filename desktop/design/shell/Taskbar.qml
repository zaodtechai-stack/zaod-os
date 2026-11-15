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
    implicitHeight: (ZaodTheme.lite || liteMode) ? ZaodTheme.taskbarHeightLite : ZaodTheme.taskbarHeight
    radius: ZaodTheme.radiusLg
    // Glass needs a compositor blur behind it; the lite profile and any host
    // without blur gets the opaque surface instead of a washed-out panel.
    color: ZaodTheme.allowGlass
        ? Qt.rgba(ZaodTheme.surface.r, ZaodTheme.surface.g, ZaodTheme.surface.b, ZaodTheme.opacityGlass)
        : ZaodTheme.surface
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
                        ? ZaodTheme.surfaceAlt : Qt.rgba(0, 0, 0, 0)
                    Behavior on color {
                        ColorAnimation { duration: ZaodTheme.motionFast; easing.type: Easing.OutCubic }
                    }
                }

                ZaodIcon {
                    anchors.centerIn: parent
                    name: modelData.iconName || ""
                    application: true
                    size: ZaodTheme.scaled(ZaodTheme.iconTaskbar)
                    fallbackGlyph: modelData.icon || "\u25A3"
                }

                Rectangle {
                    anchors.bottom: parent.bottom
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.bottomMargin: ZaodTheme.hairline
                    width: taskbar.running.indexOf(modelData.id) >= 0 ? ZaodTheme.space1 * 4 : 0
                    height: ZaodTheme.borderThick
                    radius: ZaodTheme.hairline
                    color: ZaodTheme.accent
                    Behavior on width { NumberAnimation { duration: ZaodTheme.motionFast } }
                }

                activeFocusOnTab: true
                Accessible.role: Accessible.Button
                Accessible.name: modelData.name || modelData.id
                Accessible.onPressAction: activateItem()
                Keys.onSpacePressed: activateItem()
                Keys.onReturnPressed: activateItem()

                // Focus is drawn as a token ring, never as a colour change.
                Rectangle {
                    anchors.fill: parent
                    anchors.margins: -ZaodTheme.focusRingOffset
                    radius: ZaodTheme.radiusMd + ZaodTheme.focusRingOffset
                    color: Qt.rgba(0, 0, 0, 0)
                    border.width: parent.activeFocus ? ZaodTheme.focusRingWidth : 0
                    border.color: ZaodTheme.focusRing
                    visible: parent.activeFocus
                }

                function activateItem() {
                    taskbar.activeIndex = index
                    taskbar.appActivated(modelData.id)
                }

                MouseArea {
                    id: area
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        parent.forceActiveFocus()
                        parent.activateItem()
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
