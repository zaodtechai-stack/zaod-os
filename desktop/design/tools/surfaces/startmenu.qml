// Start menu surface, opened over the desktop wallpaper.
import QtQuick 2.15
import QtQuick.Window 2.15
import "../../qml"
import "../../shell"

Window {
    width: 1366; height: 768; visible: true
    title: "startmenu"
    color: ZaodTheme.background
    // The capture harness can force lite mode and a text scale so the same
    // surface can be reviewed at the 2 GB / 1366x768 floor and at 150% text.
    Component.onCompleted: {
        ZaodTheme.mode = zaodMode
        ZaodTheme.lite = zaodLite
        ZaodTheme.fontScale = zaodScale
    }

    Image {
        anchors.fill: parent
        source: ZaodTheme.isDark
            ? "../../wallpapers/zaod-lattice-dark.svg"
            : "../../wallpapers/zaod-lattice-light.svg"
        fillMode: Image.PreserveAspectCrop
        Accessible.ignored: true
    }

    Rectangle {
        anchors.fill: parent
        color: ZaodTheme.scrim
    }

    StartMenu {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: ZaodTheme.space16 * 2
    }
}
