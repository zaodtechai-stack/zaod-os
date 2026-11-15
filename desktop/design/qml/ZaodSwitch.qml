// Zaod Fluent switch with a 120-250 ms thumb transition.
import QtQuick 2.15

Item {
    id: control

    property bool checked: false
    property string label: ""
    property bool hovered: hoverArea.containsMouse
    signal toggled(bool checked)

    activeFocusOnTab: true
    Accessible.role: Accessible.CheckBox
    Accessible.name: label
    Accessible.checked: checked
    Accessible.onToggleAction: control.toggle()

    implicitWidth: track.width + (labelText.visible ? labelText.implicitWidth + ZaodTheme.space3 : 0)
    implicitHeight: Math.max(ZaodTheme.minTargetSize, track.height)

    function toggle() {
        checked = !checked
        toggled(checked)
    }

    Keys.onSpacePressed: toggle()
    Keys.onReturnPressed: toggle()

    Rectangle {
        id: track
        width: 44
        height: 24
        radius: height / 2
        anchors.verticalCenter: parent.verticalCenter
        color: control.checked ? ZaodTheme.accent
            : control.hovered ? ZaodTheme.surfaceAlt : ZaodTheme.surfaceRaised
        border.width: ZaodTheme.hairline
        border.color: control.checked ? ZaodTheme.accent : ZaodTheme.border
        Behavior on color { ColorAnimation { duration: ZaodTheme.motionFast; easing.type: Easing.OutCubic } }

        Rectangle {
            id: thumb
            width: 16
            height: 16
            radius: height / 2
            y: (track.height - height) / 2
            x: control.checked ? track.width - width - 4 : 4
            color: control.checked ? ZaodTheme.onAccent : ZaodTheme.textSecondary
            Behavior on x { NumberAnimation { duration: ZaodTheme.motionFast; easing.type: Easing.OutCubic } }
        }
    }

    Rectangle {
        anchors.fill: track
        anchors.margins: -ZaodTheme.focusRingOffset
        radius: track.radius + ZaodTheme.focusRingOffset
        color: "transparent"
        border.width: control.activeFocus ? ZaodTheme.focusRingWidth : 0
        border.color: ZaodTheme.focusRing
    }

    Text {
        id: labelText
        anchors.left: track.right
        anchors.leftMargin: ZaodTheme.space3
        anchors.verticalCenter: parent.verticalCenter
        text: control.label
        visible: control.label.length > 0
        color: ZaodTheme.textPrimary
        font.family: ZaodTheme.fontFamily
        font.pixelSize: ZaodTheme.typeBody.size
    }

    MouseArea {
        id: hoverArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: control.toggle()
    }
}
