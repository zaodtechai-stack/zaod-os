// Zaod Fluent card: a surface with an optional title, body and footer slots.
// Elevation reads the token ladder directly (0-3), is capped by the lite
// profile, and is drawn as a shadow rather than a second border.
import QtQuick 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: card

    property string title: ""
    property string subtitle: ""
    property int elevation: 1
    property bool interactive: false
    property int padding: ZaodTheme.space4

    default property alias body: bodyColumn.data
    property alias footer: footerRow.data

    signal clicked()

    // A card may never exceed the lite cap, and never leaves the 0-3 ladder.
    readonly property int level: Math.max(0, Math.min(elevation, ZaodTheme.elevationCap))
    readonly property var shadow: level === 0 ? ZaodTheme.elevation0
        : level === 1 ? ZaodTheme.elevation1
        : level === 2 ? ZaodTheme.elevation2
        : ZaodTheme.elevation3

    radius: ZaodTheme.radiusLg
    color: ZaodTheme.surface
    border.width: ZaodTheme.hairline
    border.color: card.hovered ? ZaodTheme.borderStrong : ZaodTheme.border
    implicitWidth: ZaodTheme.space20 * 4
    implicitHeight: layout.implicitHeight + padding * 2
    activeFocusOnTab: interactive

    property bool hovered: hoverArea.containsMouse

    Accessible.role: interactive ? Accessible.Button : Accessible.Grouping
    Accessible.name: title
    Accessible.onPressAction: card.clicked()

    Rectangle {
        anchors.fill: parent
        anchors.topMargin: -card.shadow.y
        radius: parent.radius
        color: ZaodTheme.shadow
        opacity: card.shadow.opacity
        visible: card.level > 0
        z: -1
    }

    // Interactive cards get a focus ring outside the border, so focus survives
    // a colour-blind palette and any accent.
    Rectangle {
        anchors.fill: parent
        anchors.margins: -ZaodTheme.focusRingOffset
        radius: card.radius + ZaodTheme.focusRingOffset
        color: Qt.rgba(0, 0, 0, 0)
        border.width: card.activeFocus ? ZaodTheme.focusRingWidth : 0
        border.color: ZaodTheme.focusRing
        visible: card.activeFocus
    }

    Keys.onSpacePressed: if (interactive) card.clicked()
    Keys.onReturnPressed: if (interactive) card.clicked()

    ColumnLayout {
        id: layout
        anchors.fill: parent
        anchors.margins: card.padding
        spacing: ZaodTheme.space3

        Column {
            Layout.fillWidth: true
            spacing: ZaodTheme.space1
            visible: card.title.length > 0 || card.subtitle.length > 0

            Text {
                text: card.title
                visible: card.title.length > 0
                color: ZaodTheme.textPrimary
                font.family: ZaodTheme.fontFamily
                font.pixelSize: ZaodTheme.scaled(ZaodTheme.typeSubtitle.size)
                font.weight: ZaodTheme.typeSubtitle.weight
                Accessible.role: Accessible.Heading
                Accessible.name: card.title
            }
            Text {
                text: card.subtitle
                visible: card.subtitle.length > 0
                color: ZaodTheme.textSecondary
                font.family: ZaodTheme.fontFamily
                font.pixelSize: ZaodTheme.scaled(ZaodTheme.typeBodySm.size)
                wrapMode: Text.WordWrap
                width: parent.width
            }
        }

        Column {
            id: bodyColumn
            Layout.fillWidth: true
            spacing: ZaodTheme.space2
        }

        Row {
            id: footerRow
            Layout.fillWidth: true
            spacing: ZaodTheme.space2
        }
    }

    MouseArea {
        id: hoverArea
        anchors.fill: parent
        enabled: card.interactive
        hoverEnabled: true
        cursorShape: card.interactive ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: {
            card.forceActiveFocus()
            card.clicked()
        }
    }
}
