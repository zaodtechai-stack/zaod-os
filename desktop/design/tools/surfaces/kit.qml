// Component specimen sheet: every Zaod component in one surface so a theme
// change can be reviewed in a single screenshot.
import QtQuick 2.15
import QtQuick.Layouts 1.15
import QtQuick.Window 2.15
import QtQuick.Controls 2.15
import "../../qml"

Window {
    id: root
    width: 1366; height: 768; visible: true
    title: "kit"
    color: ZaodTheme.background
    // The capture harness can force lite mode and a text scale so the same
    // surface can be reviewed at the 2 GB / 1366x768 floor and at 150% text.
    Component.onCompleted: {
        ZaodTheme.mode = zaodMode
        ZaodTheme.lite = zaodLite
        ZaodTheme.fontScale = zaodScale
    }

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: ZaodTheme.space6
        spacing: ZaodTheme.space5

        RowLayout {
            Layout.fillWidth: true
            spacing: ZaodTheme.space3
            Text {
                text: qsTr("Zaod component kit")
                color: ZaodTheme.textPrimary
                font.family: ZaodTheme.fontFamily
                font.pixelSize: ZaodTheme.scaled(ZaodTheme.typeTitleLg.size)
                font.weight: ZaodTheme.typeTitleLg.weight
                Layout.fillWidth: true
                Accessible.role: Accessible.Heading
                Accessible.name: text
            }
            Text {
                text: (ZaodTheme.isDark ? "dark" : "light") + " · "
                    + Math.round(ZaodTheme.fontScale * 100) + "%"
                    + (ZaodTheme.lite ? " · lite" : "")
                color: ZaodTheme.textSecondary
                font.family: ZaodTheme.fontFamily
                font.pixelSize: ZaodTheme.scaled(ZaodTheme.typeBodySm.size)
            }
        }

        RowLayout {
            Layout.fillWidth: true
            spacing: ZaodTheme.space3
            ZaodButton { label: qsTr("Primary"); variant: ZaodButton.Variant.Primary }
            ZaodButton { label: qsTr("Secondary") }
            ZaodButton { label: qsTr("Quiet"); variant: ZaodButton.Variant.Quiet }
            ZaodButton { label: qsTr("Destructive"); variant: ZaodButton.Variant.Destructive }
            ZaodButton { label: qsTr("Disabled"); enabled: false }
            Item { Layout.fillWidth: true }
            ZaodSwitch { label: qsTr("Night light"); checked: true }
            ZaodSwitch { label: qsTr("Bluetooth") }
        }

        RowLayout {
            Layout.fillWidth: true
            Layout.fillHeight: true
            spacing: ZaodTheme.space4

            ZaodCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                title: qsTr("Elevation 0")
                subtitle: qsTr("Inline content, no shadow")
                elevation: 0
                Text { text: qsTr("Body copy on the surface role."); color: ZaodTheme.textSecondary; font.pixelSize: ZaodTheme.scaled(ZaodTheme.typeBody.size) }
            }
            ZaodCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                title: qsTr("Elevation 1")
                subtitle: qsTr("Cards, list groups")
                elevation: 1
                Text { text: qsTr("The default surface for grouped content."); color: ZaodTheme.textSecondary; font.pixelSize: ZaodTheme.scaled(ZaodTheme.typeBody.size) }
            }
            ZaodCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                title: qsTr("Elevation 2")
                subtitle: qsTr("Menus and popovers")
                elevation: 2
                Text { text: qsTr("Capped at 1 when the lite profile is on."); color: ZaodTheme.textSecondary; font.pixelSize: ZaodTheme.scaled(ZaodTheme.typeBody.size) }
            }
            ZaodCard {
                Layout.fillWidth: true
                Layout.fillHeight: true
                title: qsTr("Elevation 3")
                subtitle: qsTr("Dialogs and drawers")
                elevation: 3
                Text { text: qsTr("The highest level any component may use."); color: ZaodTheme.textSecondary; font.pixelSize: ZaodTheme.scaled(ZaodTheme.typeBody.size) }
            }
        }

        ZaodToolbar {
            Layout.fillWidth: true
            title: qsTr("Toolbar")
            actions: [
                { icon: "edit" },
                { icon: "trash" },
                { icon: "download" },
                { icon: "settings" }
            ]
        }
    }

    ZaodMenu {
        id: specimenMenu
        x: root.width - width - ZaodTheme.space6
        y: ZaodTheme.space6
        items: [
            { label: qsTr("Open"), icon: "folder" },
            { label: qsTr("Rename"), icon: "edit" },
            { label: qsTr("Delete"), icon: "trash", destructive: true }
        ]
        modal: false
        closePolicy: Popup.NoAutoClose
        visible: true
    }
}
