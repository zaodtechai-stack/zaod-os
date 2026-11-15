// Zaod Start menu: search, pinned grid and recents. Keyboard first.
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import "../qml"

Rectangle {
    id: startMenu

    property var apps: []            // [{ id, name, icon, categories }]
    property var recent: []          // [{ id, name }]
    property string query: ""

    signal launchRequested(string appId)
    signal dismissed()

    readonly property var results: {
        if (query.length === 0) return apps
        var needle = query.toLowerCase()
        return apps.filter(function (app) { return app.name.toLowerCase().indexOf(needle) >= 0 })
    }

    width: 560
    height: 600
    radius: ZaodTheme.radiusXl
    color: ZaodTheme.surfaceOverlay
    border.width: ZaodTheme.hairline
    border.color: ZaodTheme.border

    function focusSearch() {
        search.forceActiveFocus()
        search.selectAll()
    }

    Keys.onEscapePressed: startMenu.dismissed()

    ColumnLayout {
        anchors.fill: parent
        anchors.margins: ZaodTheme.space5
        spacing: ZaodTheme.space4

        TextField {
            id: search
            Layout.fillWidth: true
            placeholderText: qsTr("Search apps and settings")
            font.family: ZaodTheme.fontFamily
            font.pixelSize: ZaodTheme.typeBody.size
            color: ZaodTheme.textPrimary
            placeholderTextColor: ZaodTheme.textTertiary
            selectByMouse: true
            padding: ZaodTheme.space3
            onTextChanged: startMenu.query = text
            Keys.onDownPressed: grid.currentIndex = Math.min(grid.currentIndex + 1, grid.count - 1)
            Keys.onReturnPressed: launchCurrent()
            background: Rectangle {
                radius: ZaodTheme.radiusMd
                color: ZaodTheme.surface
                border.width: ZaodTheme.hairline
                border.color: search.activeFocus ? ZaodTheme.focusRing : ZaodTheme.border
            }
        }

        Text {
            text: qsTr("Pinned")
            color: ZaodTheme.textSecondary
            font.family: ZaodTheme.fontFamily
            font.pixelSize: ZaodTheme.typeCaption.size
            visible: startMenu.query.length === 0
        }

        GridView {
            id: grid
            Layout.fillWidth: true
            Layout.fillHeight: true
            cellWidth: width / 4
            cellHeight: cellWidth
            clip: true
            model: startMenu.results
            currentIndex: 0
            keyNavigationWraps: true

            Keys.onReturnPressed: launchCurrent()
            Keys.onEscapePressed: startMenu.dismissed()

            delegate: Item {
                width: grid.cellWidth
                height: grid.cellHeight

                Rectangle {
                    anchors.fill: parent
                    anchors.margins: ZaodTheme.space1
                    radius: ZaodTheme.radiusLg
                    color: GridView.isCurrentItem || area.containsMouse
                        ? ZaodTheme.surfaceAlt : "transparent"
                }

                Column {
                    anchors.centerIn: parent
                    spacing: ZaodTheme.space2
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: modelData.icon || "\u25A3"
                        color: ZaodTheme.textPrimary
                        font.pixelSize: 28
                    }
                    Text {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: modelData.name
                        width: grid.cellWidth - ZaodTheme.space4
                        elide: Text.ElideRight
                        horizontalAlignment: Text.AlignHCenter
                        color: ZaodTheme.textPrimary
                        font.family: ZaodTheme.fontFamily
                        font.pixelSize: ZaodTheme.typeCaption.size
                    }
                }

                MouseArea {
                    id: area
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        grid.currentIndex = index
                        startMenu.launchRequested(modelData.id)
                    }
                }
            }
        }

        RowLayout {
            Layout.fillWidth: true
            visible: startMenu.recent.length > 0 && startMenu.query.length === 0
            Text {
                text: qsTr("Recent")
                color: ZaodTheme.textSecondary
                font.family: ZaodTheme.fontFamily
                font.pixelSize: ZaodTheme.typeCaption.size
            }
            Repeater {
                model: startMenu.recent
                delegate: ZaodButton {
                    variant: ZaodButton.Variant.Quiet
                    label: modelData.name
                    onClicked: startMenu.launchRequested(modelData.id)
                }
            }
            Item { Layout.fillWidth: true }
        }
    }

    function launchCurrent() {
        if (grid.currentIndex >= 0 && grid.currentIndex < startMenu.results.length) {
            startMenu.launchRequested(startMenu.results[grid.currentIndex].id)
        }
    }
}
