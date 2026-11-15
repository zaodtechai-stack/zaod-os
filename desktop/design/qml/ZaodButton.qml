// Zaod Fluent button. Variants: primary, secondary, quiet, destructive.
import QtQuick 2.15
import QtQuick.Controls 2.15

Control {
    id: control

    enum Variant { Primary, Secondary, Quiet, Destructive }

    property int variant: ZaodButton.Variant.Secondary
    property string label: ""
    property bool loading: false
    property int size: ZaodTheme.minTargetSize

    readonly property color _background: {
        switch (variant) {
        case ZaodButton.Variant.Primary:
            return isPressed ? ZaodTheme.accentPressed
                : isHovered ? ZaodTheme.accentHover : ZaodTheme.accent
        case ZaodButton.Variant.Destructive:
            return ZaodTheme.danger
        case ZaodButton.Variant.Quiet:
            return isHovered ? ZaodTheme.surfaceAlt : "transparent"
        default:
            return isPressed ? ZaodTheme.surfaceAlt
                : isHovered ? ZaodTheme.surfaceRaised : ZaodTheme.surface
        }
    }

    readonly property color _foreground: {
        if (variant === ZaodButton.Variant.Primary) return ZaodTheme.onAccent
        if (variant === ZaodButton.Variant.Destructive) return ZaodTheme.onDanger
        return ZaodTheme.textPrimary
    }

    readonly property color _border: {
        if (variant === ZaodButton.Variant.Quiet) return Qt.rgba(0, 0, 0, 0)
        if (variant === ZaodButton.Variant.Primary) return ZaodTheme.accent
        if (variant === ZaodButton.Variant.Destructive) return ZaodTheme.danger
        return ZaodTheme.border
    }

    // `Control` owns a FINAL `hovered`; the component tracks its own state.
    readonly property bool isHovered: hoverArea.containsMouse || hoverHandler.hovered
    readonly property bool isPressed: tapHandler.pressed
    signal clicked()

    // Full keyboard support: Space/Enter activate, Tab moves on.
    activeFocusOnTab: true
    Accessible.role: Accessible.Button
    Accessible.name: label
    Accessible.onPressAction: control.clicked()

    implicitWidth: Math.max(ZaodTheme.minTargetSize, row.implicitWidth + ZaodTheme.space5 * 2)
    implicitHeight: Math.max(size, ZaodTheme.minTargetSize)
    opacity: enabled ? 1.0 : 0.45
    enabled: !loading

    hoverEnabled: true
    Keys.onSpacePressed: control.clicked()
    Keys.onReturnPressed: control.clicked()

    background: Rectangle {
        radius: ZaodTheme.radiusMd
        color: control._background
        border.width: control.variant === ZaodButton.Variant.Quiet ? 0 : ZaodTheme.hairline
        border.color: control._border
        Behavior on color { ColorAnimation { duration: ZaodTheme.motionFast; easing.type: Easing.OutCubic } }
    }

    contentItem: Row {
        id: row
        spacing: ZaodTheme.space2
        anchors.centerIn: parent
        Text {
            visible: control.loading
            text: "\u25CF"
            color: control._foreground
            font.pixelSize: ZaodTheme.scaled(ZaodTheme.typeCaption.size)
            SequentialAnimation on opacity {
                running: control.loading
                loops: Animation.Infinite
                NumberAnimation { to: 0.3; duration: ZaodTheme.motionSlow }
                NumberAnimation { to: 1.0; duration: ZaodTheme.motionSlow }
            }
        }
        Text {
            text: control.label
            color: control._foreground
            font.family: ZaodTheme.fontFamily
            font.pixelSize: ZaodTheme.typeBody.size
            font.weight: Font.Medium
            verticalAlignment: Text.AlignVCenter
        }
    }

    // Focus ring, drawn outside the background so it never shifts the layout.
    Rectangle {
        anchors.fill: parent
        anchors.margins: -ZaodTheme.focusRingOffset
        radius: ZaodTheme.radiusMd + ZaodTheme.focusRingOffset
        color: "transparent"
        border.width: control.activeFocus ? ZaodTheme.focusRingWidth : 0
        border.color: ZaodTheme.focusRing
        visible: control.activeFocus
    }

    MouseArea {
        id: hoverArea
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: control.clicked()
    }

    HoverHandler { id: hoverHandler }
    TapHandler { id: tapHandler }
}
