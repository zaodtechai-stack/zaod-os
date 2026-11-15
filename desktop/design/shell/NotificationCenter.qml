// Zaod notification centre and calendar strip.
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../qml"

Rectangle {
    id: center

    property var notifications: []   // [{ id, app, title, body, time }]
    property var calendar: ({ weekday: 0, day: 1, month: "", nextEvents: [] })

    signal dismissed(string notificationId)
    signal clearAllRequested()
    signal eventRequested(int index)

    width: ZaodTheme.notificationWidth
    implicitHeight: layout.implicitHeight + ZaodTheme.space5 * 2
    radius: ZaodTheme.radiusXl
    color: ZaodTheme.surfaceOverlay
    border.width: ZaodTheme.hairline
    border.color: ZaodTheme.border

    ColumnLayout {
        id: layout
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: ZaodTheme.space5
        spacing: ZaodTheme.space3

        RowLayout {
            Layout.fillWidth: true
            Text {
                text: Qt.formatDateTime(new Date(), "dddd d MMMM")
                color: ZaodTheme.textPrimary
                font.family: ZaodTheme.fontFamily
                font.pixelSize: ZaodTheme.scaled(ZaodTheme.typeSubtitle.size)
                font.weight: ZaodTheme.typeSubtitle.weight
            }
            Item { Layout.fillWidth: true }
            ZaodButton {
                variant: ZaodButton.Variant.Quiet
                label: qsTr("Clear all")
                enabled: center.notifications.length > 0
                onClicked: center.clearAllRequested()
            }
        }

        Column {
            Layout.fillWidth: true
            spacing: ZaodTheme.space2
            visible: center.calendar.nextEvents.length > 0
            Repeater {
                model: center.calendar.nextEvents
                delegate: Row {
                    spacing: ZaodTheme.space3
                    Rectangle {
                        width: ZaodTheme.borderThick
                        height: ZaodTheme.space6
                        color: ZaodTheme.accent
                        radius: ZaodTheme.hairline
                    }
                    Column {
                        Text {
                            text: modelData.time || ""
                            color: ZaodTheme.textSecondary
                            font.family: ZaodTheme.fontFamilyMono
                            font.pixelSize: ZaodTheme.scaled(ZaodTheme.typeCaption.size)
                        }
                        Text {
                            text: modelData.title || ""
                            color: ZaodTheme.textPrimary
                            font.family: ZaodTheme.fontFamily
                            font.pixelSize: ZaodTheme.scaled(ZaodTheme.typeBody.size)
                        }
                    }
                }
            }
        }

        Rectangle {
            Layout.fillWidth: true
            height: ZaodTheme.hairline
            color: ZaodTheme.border
        }

        Text {
            text: qsTr("Notifications")
            color: ZaodTheme.textSecondary
            font.family: ZaodTheme.fontFamily
            font.pixelSize: ZaodTheme.scaled(ZaodTheme.typeCaption.size)
        }

        Column {
            id: list
            Layout.fillWidth: true
            spacing: ZaodTheme.space2

            Repeater {
                model: center.notifications
                delegate: ZaodCard {
                    width: list.width
                    title: modelData.title
                    subtitle: modelData.body
                    elevation: 0
                    padding: ZaodTheme.space3

                    Row {
                        spacing: ZaodTheme.space2
                        Text {
                            text: modelData.app
                            color: ZaodTheme.textTertiary
                            font.family: ZaodTheme.fontFamily
                            font.pixelSize: ZaodTheme.scaled(ZaodTheme.typeCaption.size)
                        }
                        Text {
                            text: modelData.time
                            color: ZaodTheme.textTertiary
                            font.family: ZaodTheme.fontFamilyMono
                            font.pixelSize: ZaodTheme.scaled(ZaodTheme.typeCaption.size)
                        }
                    }

                    ZaodButton {
                        variant: ZaodButton.Variant.Quiet
                        label: qsTr("Dismiss")
                        onClicked: center.dismissed(modelData.id)
                    }
                }
            }

            Text {
                visible: center.notifications.length === 0
                width: list.width
                horizontalAlignment: Text.AlignHCenter
                text: qsTr("Nothing needs your attention")
                color: ZaodTheme.textTertiary
                font.family: ZaodTheme.fontFamily
                font.pixelSize: ZaodTheme.scaled(ZaodTheme.typeBodySm.size)
                padding: ZaodTheme.space6
            }
        }
    }
}
