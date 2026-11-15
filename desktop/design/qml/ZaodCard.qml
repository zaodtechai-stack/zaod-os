// Zaod Fluent card: a surface with an optional title, body and footer slots.
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

    radius: ZaodTheme.radiusLg
    color: ZaodTheme.surface
    border.width: ZaodTheme.hairline
    border.color: ZaodTheme.border
    implicitWidth: 320
    implicitHeight: layout.implicitHeight + padding * 2

    // Elevation is a soft shadow rather than a second border.
    Rectangle {
        anchors.fill: parent
        anchors.topMargin: -ZaodTheme.elevation2.y
        radius: parent.radius
        color: ZaodTheme.shadow
        opacity: ZaodTheme.elevation2.opacity * (card.elevation / 4)
        z: -1
    }

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
                font.pixelSize: ZaodTheme.typeSubtitle.size
                font.weight: Font.DemiBold
            }
            Text {
                text: card.subtitle
                visible: card.subtitle.length > 0
                color: ZaodTheme.textSecondary
                font.family: ZaodTheme.fontFamily
                font.pixelSize: ZaodTheme.typeBodySm.size
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
        anchors.fill: parent
        enabled: card.interactive
        hoverEnabled: true
        cursorShape: card.interactive ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: card.clicked()
    }
}
