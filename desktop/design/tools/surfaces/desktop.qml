// Desktop surface: wallpaper plus the taskbar, at the 1366x768 floor.
import QtQuick 2.15
import QtQuick.Window 2.15
import "../../qml"
import "../../shell"

Window {
    id: root
    width: 1366; height: 768; visible: true
    title: "desktop"
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
            ? "../../wallpapers/zaod-aurora-dark.svg"
            : "../../wallpapers/zaod-aurora-light.svg"
        fillMode: Image.PreserveAspectCrop
        smooth: true
        Accessible.ignored: true
    }

    Taskbar {
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: ZaodTheme.space3
        width: Math.min(parent.width - ZaodTheme.space8, 720)
    }
}
