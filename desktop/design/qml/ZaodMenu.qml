// Zaod Fluent menu: a keyboard-navigable list of items with separators.
import QtQuick 2.15
import QtQuick.Controls 2.15

Popup {
    id: menu

    property var items: []          // [{ label, shortcut, enabled, separator }]
    property int currentIndex: -1
    signal activated(int index)

    padding: ZaodTheme.space1
    modal: true
    closePolicy: Popup.CloseOnEscape | Popup.CloseOnPressOutside
    width: ZaodTheme.menuWidth

    // Menus are elevation level 2; the lite profile caps them at 1 and the
    // shadow rectangle collapses because the level is read from the ladder.
    readonly property var shadowSpec: ZaodTheme.elevationCap >= 2
        ? ZaodTheme.elevation2 : ZaodTheme.elevation1

    background: Item {
        Rectangle {
            anchors.fill: parent
            anchors.topMargin: -menu.shadowSpec.y
            radius: ZaodTheme.radiusMd
            color: ZaodTheme.shadow
            opacity: menu.shadowSpec.opacity
            z: -1
        }
        Rectangle {
            anchors.fill: parent
            color: ZaodTheme.surfaceOverlay
            radius: ZaodTheme.radiusMd
            border.width: ZaodTheme.hairline
            border.color: ZaodTheme.border
        }
    }

    contentItem: Column {
        focus: true
        Keys.onDownPressed: menu.move(1)
        Keys.onUpPressed: menu.move(-1)
        Keys.onReturnPressed: {
            if (menu.currentIndex >= 0) {
                menu.activated(menu.currentIndex)
                menu.close()
            }
        }
        spacing: ZaodTheme.space0
        Repeater {
            model: menu.items
            delegate: Item {
                id: entry
                width: menu.availableWidth
                height: modelData.separator ? ZaodTheme.space2
                    : Math.max(ZaodTheme.minTargetSize, ZaodTheme.typeBody.lineHeight + ZaodTheme.space2 * 2)

                Rectangle {
                    visible: modelData.separator === true
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width - ZaodTheme.space2
                    height: ZaodTheme.hairline
                    color: ZaodTheme.border
                }

                Rectangle {
                    visible: !modelData.separator
                    anchors.fill: parent
                    radius: ZaodTheme.radiusSm
                    color: entryMouse.containsMouse || menu.currentIndex === index
                        ? ZaodTheme.accentSubtle : Qt.rgba(0, 0, 0, 0)
                    border.width: menu.currentIndex === index && menu.contentItem.activeFocus
                        ? ZaodTheme.focusRingWidth : 0
                    border.color: ZaodTheme.focusRing
                }

                Row {
                    visible: !modelData.separator
                    anchors.fill: parent
                    anchors.leftMargin: ZaodTheme.space2
                    anchors.rightMargin: ZaodTheme.space2
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.label || ""
                        color: modelData.enabled === false ? ZaodTheme.textDisabled : ZaodTheme.textPrimary
                        font.family: ZaodTheme.fontFamily
                        font.pixelSize: ZaodTheme.scaled(ZaodTheme.typeBody.size)
                        opacity: modelData.enabled === false ? 0.6 : 1.0
                    }
                    Item { width: parent.width - ZaodTheme.space16; height: ZaodTheme.hairline }
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        text: modelData.shortcut || ""
                        color: ZaodTheme.textTertiary
                        font.family: ZaodTheme.fontFamilyMono
                        font.pixelSize: ZaodTheme.scaled(ZaodTheme.typeCaption.size)
                    }
                }

                MouseArea {
                    id: entryMouse
                    anchors.fill: parent
                    hoverEnabled: true
                    enabled: modelData.separator !== true && modelData.enabled !== false
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        menu.activated(index)
                        menu.close()
                    }
                }
            }
        }
    }

    function move(delta) {
        var next = menu.currentIndex
        for (var step = 0; step < menu.items.length; step++) {
            next = (next + delta + menu.items.length) % menu.items.length
            if (!menu.items[next].separator && menu.items[next].enabled !== false) break
        }
        menu.currentIndex = next
    }

}
