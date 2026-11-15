// Zaod icon: resolves a generated icon name to the light or dark SVG the token
// set produced, so no surface has to carry a glyph copy of the icon library.
import QtQuick 2.15

Item {
    id: icon

    // A name from desktop/design/icons/icons.json, for example "network" or "notes".
    property string name: ""
    property bool application: false
    property int size: application ? ZaodTheme.iconApp : ZaodTheme.iconNav
    // Kept for callers that still hand over a unicode glyph.
    property string fallbackGlyph: ""

    readonly property string folder: application ? "app" : "nav"
    readonly property string themeSuffix: ZaodTheme.isDark ? "dark" : "light"
    readonly property url source: name.length > 0
        ? "../icons/" + folder + "/" + name + "-" + themeSuffix + ".svg"
        : ""

    implicitWidth: size
    implicitHeight: size
    Accessible.role: Accessible.Graphic
    Accessible.name: name

    Image {
        id: glyphImage
        anchors.fill: parent
        source: icon.source
        sourceSize.width: icon.size
        sourceSize.height: icon.size
        fillMode: Image.PreserveAspectFit
        smooth: true
        visible: status === Image.Ready
        // The icon files are already theme-coloured; no tint pass is needed,
        // which keeps them cheap on a 2 GB machine.
        Accessible.ignored: true
    }

    Text {
        anchors.centerIn: parent
        visible: glyphImage.status !== Image.Ready && icon.fallbackGlyph.length > 0
        text: icon.fallbackGlyph
        color: ZaodTheme.textPrimary
        font.pixelSize: ZaodTheme.scaled(icon.size)
    }
}
