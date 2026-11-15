// Zaod Fluent toolbar: a slim surface hosting a leading title, actions and overflow.
import QtQuick 2.15

Rectangle {
    id: toolbar

    property string title: ""
    property string subtitle: ""

    default property alias actions: actionRow.data
    property alias leading: leadingRow.data

    implicitHeight: Math.max(ZaodTheme.minTargetSize, ZaodTheme.space12)
    color: ZaodTheme.surface
    radius: ZaodTheme.radiusLg
    border.width: ZaodTheme.hairline
    border.color: ZaodTheme.border

    Row {
        id: leadingRow
        anchors.left: parent.left
        anchors.leftMargin: ZaodTheme.space3
        anchors.verticalCenter: parent.verticalCenter
        spacing: ZaodTheme.space2
    }

    Column {
        id: titleBlock
        anchors.left: leadingRow.right
        anchors.leftMargin: leadingRow.children.length > 0 ? ZaodTheme.space3 : ZaodTheme.space4
        anchors.verticalCenter: parent.verticalCenter
        spacing: 0

        Text {
            text: toolbar.title
            color: ZaodTheme.textPrimary
            font.family: ZaodTheme.fontFamily
            font.pixelSize: ZaodTheme.typeBodyStrong.size
            font.weight: Font.DemiBold
            visible: toolbar.title.length > 0
        }
        Text {
            text: toolbar.subtitle
            color: ZaodTheme.textSecondary
            font.family: ZaodTheme.fontFamily
            font.pixelSize: ZaodTheme.typeCaption.size
            visible: toolbar.subtitle.length > 0
        }
    }

    Row {
        id: actionRow
        anchors.right: parent.right
        anchors.rightMargin: ZaodTheme.space3
        anchors.verticalCenter: parent.verticalCenter
        spacing: ZaodTheme.space2
    }
}
