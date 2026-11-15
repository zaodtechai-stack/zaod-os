// GENERATED FILE - do not edit.
// Source: desktop/design/tokens/tokens.json
// Generator: desktop/design/tools/tokens_to_qml.py
pragma Singleton
import QtQuick 2.15

QtObject {
    id: theme

    // Mode: use ZaodTheme.mode = "light" | "dark" to switch at runtime.
    property string mode: "dark"
    readonly property bool isDark: mode === "dark"

    // Lite profile: 1366x768 / 2 GB / 2 cores. Set by the session, never by an app.
    property bool lite: false
    readonly property int elevationCap: lite ? 1 : 3
    readonly property bool allowBlur: !lite && false
    readonly property bool allowGlass: !lite && false
    readonly property bool allowAnimation: !lite && false
    readonly property bool allowPreviews: !lite && false
    readonly property bool allowThumbnails: false

    // Text scale: 1.0 to 1.5. Every pixelSize goes through scaled().
    property real fontScale: 1.0
    readonly property real minFontScale: 1.0
    readonly property real maxFontScale: 1.5

    function scaled(pixels) {
        return Math.round(pixels * fontScale)
    }

    function lineHeight(step) {
        return Math.round(step.lineHeight * fontScale)
    }

    // Motion: 0 ms whenever the lite profile or the session disables animation.
    function duration(milliseconds) {
        return allowAnimation ? milliseconds : 0
    }

    readonly property int grid: 4

    readonly property int space0: 0
    readonly property int space1: 4
    readonly property int space2: 8
    readonly property int space3: 12
    readonly property int space4: 16
    readonly property int space5: 20
    readonly property int space6: 24
    readonly property int space7: 28
    readonly property int space8: 32
    readonly property int space10: 40
    readonly property int space12: 48
    readonly property int space16: 64
    readonly property int space20: 80
    readonly property int space24: 96

    readonly property int radiusNone: 0
    readonly property int radiusSm: 4
    readonly property int radiusMd: 8
    readonly property int radiusLg: 12
    readonly property int radiusXl: 16
    readonly property int radiusXxl: 24
    readonly property int radiusPill: 999

    readonly property int hairline: 1
    readonly property int borderThick: 2
    readonly property int focusRingWidth: 2
    readonly property int focusRingOffset: 2
    readonly property int minTargetSize: 32
    readonly property int minPointerTarget: 28

    readonly property int taskbarHeight: 44
    readonly property int taskbarHeightLite: 40
    readonly property int taskbarItemCount: 8
    readonly property int startMenuWidth: 560
    readonly property int startMenuHeight: 600
    readonly property int quickSettingsWidth: 380
    readonly property int notificationWidth: 400
    readonly property int menuWidth: 256
    readonly property int windowChromeHeight: 40
    readonly property int windowMinWidth: 480
    readonly property int windowMinHeight: 320
    readonly property int iconNav: 24
    readonly property int iconApp: 64
    readonly property int iconGridCell: 96
    readonly property int iconStartMenu: 28
    readonly property int iconTaskbar: 20

    readonly property real opacityGlass: 0.92
    readonly property real opacityScrim: 0.48
    readonly property real opacityHover: 0.08
    readonly property real opacityPressed: 0.12
    readonly property real opacityDisabled: 0.45
    readonly property real opacityHint: 0.6

    readonly property int motionFast: 120
    readonly property int motionBase: 160
    readonly property int motionSlow: 250
    readonly property string motionEasing: "cubic-bezier(0.2, 0, 0, 1)"

    readonly property string fontFamily: "Inter"
    readonly property string fontFamilyDisplay: "Inter"
    readonly property string fontFamilyMono: "JetBrains Mono"

    readonly property var typeCaption: ({ size: 11, lineHeight: 16, weight: 400, tracking: 0.2 })
    readonly property var typeBodySm: ({ size: 12, lineHeight: 16, weight: 400, tracking: 0.1 })
    readonly property var typeBody: ({ size: 14, lineHeight: 20, weight: 400, tracking: 0.0 })
    readonly property var typeBodyStrong: ({ size: 14, lineHeight: 20, weight: 600, tracking: 0.0 })
    readonly property var typeSubtitle: ({ size: 16, lineHeight: 24, weight: 600, tracking: 0.0 })
    readonly property var typeTitle: ({ size: 20, lineHeight: 28, weight: 600, tracking: -0.1 })
    readonly property var typeTitleLg: ({ size: 24, lineHeight: 32, weight: 600, tracking: -0.2 })
    readonly property var typeDisplay: ({ size: 32, lineHeight: 40, weight: 600, tracking: -0.4 })

    readonly property var elevation0: ({ blur: 0, y: 0, opacity: 0.0 })
    readonly property var elevation1: ({ blur: 4, y: 1, opacity: 0.08 })
    readonly property var elevation2: ({ blur: 12, y: 2, opacity: 0.12 })
    readonly property var elevation3: ({ blur: 24, y: 6, opacity: 0.16 })
    readonly property var elevation4: ({ blur: 40, y: 12, opacity: 0.2 })

    // Palette: light and dark are both generated so a theme switch is instant.
    readonly property var lightPalette: ({
        background: "#F6F7F9",
        surface: "#FFFFFF",
        surfaceAlt: "#EEF1F5",
        surfaceRaised: "#FFFFFF",
        surfaceOverlay: "#FFFFFF",
        border: "#818A98",
        borderStrong: "#5F6875",
        textPrimary: "#101418",
        textSecondary: "#4A5260",
        textTertiary: "#5F6875",
        textDisabled: "#8A93A0",
        accent: "#0067C0",
        accentHover: "#005BA8",
        accentPressed: "#004F91",
        accentSubtle: "#E6F0FB",
        onAccent: "#FFFFFF",
        danger: "#B3261E",
        onDanger: "#FFFFFF",
        success: "#1B6B3A",
        warning: "#7A5900",
        focusRing: "#0067C0",
        shadow: "#0B1B2B",
        scrim: "#0B1B2B"
    })

    readonly property var darkPalette: ({
        background: "#14161A",
        surface: "#1B1E23",
        surfaceAlt: "#23272E",
        surfaceRaised: "#282D35",
        surfaceOverlay: "#2E343D",
        border: "#737F90",
        borderStrong: "#8A93A0",
        textPrimary: "#F2F4F7",
        textSecondary: "#B4BCC8",
        textTertiary: "#9CA6B3",
        textDisabled: "#6C7684",
        accent: "#4CC2FF",
        accentHover: "#6BCEFF",
        accentPressed: "#8AD8FF",
        accentSubtle: "#16303F",
        onAccent: "#101418",
        danger: "#FFB4AB",
        onDanger: "#3B0906",
        success: "#7DDC9B",
        warning: "#F5C451",
        focusRing: "#4CC2FF",
        shadow: "#000000",
        scrim: "#000000"
    })

    readonly property var palette: isDark ? darkPalette : lightPalette

    readonly property color background: palette.background
    readonly property color surface: palette.surface
    readonly property color surfaceAlt: palette.surfaceAlt
    readonly property color surfaceRaised: palette.surfaceRaised
    readonly property color surfaceOverlay: palette.surfaceOverlay
    readonly property color border: palette.border
    readonly property color borderStrong: palette.borderStrong
    readonly property color textPrimary: palette.textPrimary
    readonly property color textSecondary: palette.textSecondary
    readonly property color textTertiary: palette.textTertiary
    readonly property color textDisabled: palette.textDisabled
    readonly property color accent: palette.accent
    readonly property color accentHover: palette.accentHover
    readonly property color accentPressed: palette.accentPressed
    readonly property color accentSubtle: palette.accentSubtle
    readonly property color onAccent: palette.onAccent
    readonly property color danger: palette.danger
    readonly property color onDanger: palette.onDanger
    readonly property color success: palette.success
    readonly property color warning: palette.warning
    readonly property color focusRing: palette.focusRing
    readonly property color shadow: palette.shadow

    readonly property color scrimBase: palette.scrim
    readonly property color scrim: Qt.rgba(scrimBase.r, scrimBase.g, scrimBase.b, opacityScrim)

    function withAlpha(color, alpha) {
        return Qt.rgba(color.r, color.g, color.b, alpha)
    }

    function toggleMode() {
        mode = isDark ? "light" : "dark"
    }
}
