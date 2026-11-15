// Zaod quick settings: connectivity toggles, volume, brightness and power.
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../qml"

Rectangle {
    id: quick

    property bool wifiEnabled: true
    property bool bluetoothEnabled: false
    property bool nightLight: false
    property bool airplaneMode: false
    property real volume: 0.6
    property real brightness: 0.8
    property int batteryPercent: 100
    property bool charging: false
    property string networkName: ""

    signal toggled(string key, bool value)
    signal volumeRequested(real value)
    signal brightnessRequested(real value)
    signal settingsRequested()
    signal lockRequested()

    width: ZaodTheme.quickSettingsWidth
    implicitHeight: column.implicitHeight + ZaodTheme.space5 * 2
    radius: ZaodTheme.radiusXl
    color: ZaodTheme.surfaceOverlay
    border.width: ZaodTheme.hairline
    border.color: ZaodTheme.border

    component Tile: Rectangle {
        id: tile
        property string glyph: ""
        property string iconName: ""
        property string text: ""
        property bool checked: false
        signal clicked()
        radius: ZaodTheme.radiusMd
        color: tile.checked ? ZaodTheme.accent : ZaodTheme.surface
        border.width: ZaodTheme.hairline
        border.color: tile.checked ? ZaodTheme.accent : ZaodTheme.border
        implicitHeight: ZaodTheme.space12
        implicitWidth: ZaodTheme.space16 + ZaodTheme.space6
        activeFocusOnTab: true
        Accessible.role: Accessible.Button
        Accessible.name: tile.text
        Accessible.checkable: true
        Accessible.checked: tile.checked
        Accessible.onPressAction: tile.clicked()
        Keys.onSpacePressed: tile.clicked()
        Keys.onReturnPressed: tile.clicked()

        Rectangle {
            anchors.fill: parent
            anchors.margins: -ZaodTheme.focusRingOffset
            radius: tile.radius + ZaodTheme.focusRingOffset
            color: Qt.rgba(0, 0, 0, 0)
            border.width: tile.activeFocus ? ZaodTheme.focusRingWidth : 0
            border.color: ZaodTheme.focusRing
            visible: tile.activeFocus
        }

        Row {
            anchors.centerIn: parent
            spacing: ZaodTheme.space2
            ZaodIcon {
                name: tile.iconName
                size: ZaodTheme.scaled(ZaodTheme.iconNav)
                fallbackGlyph: tile.glyph
            }
            Text {
                text: tile.text
                color: tile.checked ? ZaodTheme.onAccent : ZaodTheme.textPrimary
                font.family: ZaodTheme.fontFamily
                font.pixelSize: ZaodTheme.scaled(ZaodTheme.typeCaption.size)
            }
        }

        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            cursorShape: Qt.PointingHandCursor
            onClicked: {
                tile.forceActiveFocus()
                tile.clicked()
            }
        }
    }

    component Slider: Item {
        id: sliderRow
        property string glyph: ""
        property real value: 0.5
        property bool adjustable: true
        signal moved(real value)
        implicitHeight: ZaodTheme.minTargetSize

        Text {
            id: glyphText
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
            text: sliderRow.glyph
            color: ZaodTheme.textSecondary
            font.pixelSize: ZaodTheme.scaled(ZaodTheme.typeBodySm.size)
        }

        Rectangle {
            id: track
            anchors.left: glyphText.right
            anchors.leftMargin: ZaodTheme.space3
            anchors.right: parent.right
            anchors.verticalCenter: parent.verticalCenter
            height: ZaodTheme.space1
            radius: height / 2
            color: ZaodTheme.surfaceAlt

            Rectangle {
                width: track.width * sliderRow.value
                height: parent.height
                radius: parent.radius
                color: ZaodTheme.accent
            }

            Rectangle {
                id: handle
                x: Math.max(0, Math.min(track.width - width, track.width * sliderRow.value - width / 2))
                anchors.verticalCenter: parent.verticalCenter
                width: ZaodTheme.space4
                height: width
                radius: width / 2
                color: ZaodTheme.accent
                border.width: 2
                border.color: ZaodTheme.surface
            }
        }

        MouseArea {
            anchors.fill: parent
            enabled: sliderRow.adjustable
            onPositionChanged: {
                var start = glyphText.width + ZaodTheme.space3
                var ratio = (mouse.x - start) / Math.max(1, track.width)
                sliderRow.moved(Math.max(0, Math.min(1, ratio)))
            }
        }
    }

    ColumnLayout {
        id: column
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.margins: ZaodTheme.space5
        spacing: ZaodTheme.space3

        RowLayout {
            Layout.fillWidth: true
            Tile {
                glyph: "\u2248"
                text: qsTr("Wi-Fi")
                checked: quick.wifiEnabled && !quick.airplaneMode
                onClicked: quick.toggled("wifi", !quick.wifiEnabled)
            }
            Tile {
                glyph: "\u25C8"
                text: qsTr("Bluetooth")
                checked: quick.bluetoothEnabled && !quick.airplaneMode
                onClicked: quick.toggled("bluetooth", !quick.bluetoothEnabled)
            }
        }

        RowLayout {
            Layout.fillWidth: true
            Tile {
                glyph: "\u25D1"
                text: qsTr("Night light")
                checked: quick.nightLight
                onClicked: quick.toggled("nightLight", !quick.nightLight)
            }
            Tile {
                glyph: "\u2708"
                text: qsTr("Airplane")
                checked: quick.airplaneMode
                onClicked: quick.toggled("airplane", !quick.airplaneMode)
            }
        }

        Slider {
            Layout.fillWidth: true
            glyph: "\u25B6"
            value: quick.volume
            onMoved: quick.volumeRequested(value)
        }

        Slider {
            Layout.fillWidth: true
            glyph: "\u2600"
            value: quick.brightness
            onMoved: quick.brightnessRequested(value)
        }

        Rectangle {
            Layout.fillWidth: true
            height: ZaodTheme.hairline
            color: ZaodTheme.border
        }

        RowLayout {
            Layout.fillWidth: true
            Text {
                text: quick.charging
                    ? qsTr("%1% and charging").arg(quick.batteryPercent)
                    : qsTr("%1% battery").arg(quick.batteryPercent)
                color: ZaodTheme.textSecondary
                font.family: ZaodTheme.fontFamily
                font.pixelSize: ZaodTheme.scaled(ZaodTheme.typeCaption.size)
            }
            Item { Layout.fillWidth: true }
            ZaodButton {
                variant: ZaodButton.Variant.Quiet
                label: qsTr("Settings")
                onClicked: quick.settingsRequested()
            }
            ZaodButton {
                variant: ZaodButton.Variant.Quiet
                label: qsTr("Lock")
                onClicked: quick.lockRequested()
            }
        }

        Text {
            Layout.fillWidth: true
            text: quick.networkName.length > 0
                ? qsTr("Connected to %1").arg(quick.networkName)
                : qsTr("No network connection")
            color: ZaodTheme.textTertiary
            font.family: ZaodTheme.fontFamily
            font.pixelSize: ZaodTheme.scaled(ZaodTheme.typeCaption.size)
            elide: Text.ElideRight
        }
    }
}
