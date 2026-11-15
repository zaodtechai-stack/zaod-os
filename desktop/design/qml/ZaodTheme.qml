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

    readonly property int motionFast: 120
    readonly property int motionBase: 160
    readonly property int motionSlow: 250
    readonly property string motionEasing: "cubic-bezier(0.2, 0, 0, 1)"

    readonly property string fontFamily: "Inter"
    readonly property string fontFamilyDisplay: "Inter"
    readonly property string fontFamilyMono: "JetBrains Mono"

    readonly property var typeCaption: ({ size: 11, lineHeight: 16, weight: 400, tracking: 0.2 })
    readonly property var typeBodysm: ({ size: 12, lineHeight: 16, weight: 400, tracking: 0.1 })
    readonly property var typeBody: ({ size: 14, lineHeight: 20, weight: 400, tracking: 0.0 })
    readonly property var typeBodystrong: ({ size: 14, lineHeight: 20, weight: 600, tracking: 0.0 })
    readonly property var typeSubtitle: ({ size: 16, lineHeight: 24, weight: 600, tracking: 0.0 })
    readonly property var typeTitle: ({ size: 20, lineHeight: 28, weight: 600, tracking: -0.1 })
    readonly property var typeTitlelg: ({ size: 24, lineHeight: 32, weight: 600, tracking: -0.2 })
    readonly property var typeDisplay: ({ size: 32, lineHeight: 40, weight: 600, tracking: -0.4 })

    readonly property var elevation0: ({ blur: 0, y: 0, opacity: 0.0 })
    readonly property var elevation1: ({ blur: 4, y: 1, opacity: 0.08 })
    readonly property var elevation2: ({ blur: 12, y: 2, opacity: 0.12 })
    readonly property var elevation3: ({ blur: 24, y: 6, opacity: 0.16 })
    readonly property var elevation4: ({ blur: 40, y: 12, opacity: 0.2 })

    // Palette: light and dark are both generated so a theme switch is instant.
    readonly property var lightPalette: ({
    readonly property color background: "#F6F7F9"
    readonly property color surface: "#FFFFFF"
    readonly property color surfaceAlt: "#EEF1F5"
    readonly property color surfaceRaised: "#FFFFFF"
    readonly property color surfaceOverlay: "#FFFFFF"
    readonly property color border: "#848D9A"
    readonly property color borderStrong: "#5F6875"
    readonly property color textPrimary: "#101418"
    readonly property color textSecondary: "#4A5260"
    readonly property color textTertiary: "#5F6875"
    readonly property color textDisabled: "#8A93A0"
    readonly property color accent: "#0067C0"
    readonly property color accentHover: "#005BA8"
    readonly property color accentPressed: "#004F91"
    readonly property color accentSubtle: "#E6F0FB"
    readonly property color onAccent: "#FFFFFF"
    readonly property color danger: "#B3261E"
    readonly property color onDanger: "#FFFFFF"
    readonly property color success: "#1B6B3A"
    readonly property color warning: "#7A5900"
    readonly property color focusRing: "#0067C0"
    readonly property color shadow: "#0B1B2B"
    readonly property color scrim: "#0B1B2B"
    })

    readonly property var darkPalette: ({
    readonly property color background: "#14161A"
    readonly property color surface: "#1B1E23"
    readonly property color surfaceAlt: "#23272E"
    readonly property color surfaceRaised: "#282D35"
    readonly property color surfaceOverlay: "#2E343D"
    readonly property color border: "#626C7B"
    readonly property color borderStrong: "#8A93A0"
    readonly property color textPrimary: "#F2F4F7"
    readonly property color textSecondary: "#B4BCC8"
    readonly property color textTertiary: "#9CA6B3"
    readonly property color textDisabled: "#6C7684"
    readonly property color accent: "#4CC2FF"
    readonly property color accentHover: "#6BCEFF"
    readonly property color accentPressed: "#8AD8FF"
    readonly property color accentSubtle: "#16303F"
    readonly property color onAccent: "#101418"
    readonly property color danger: "#FFB4AB"
    readonly property color onDanger: "#3B0906"
    readonly property color success: "#7DDC9B"
    readonly property color warning: "#F5C451"
    readonly property color focusRing: "#4CC2FF"
    readonly property color shadow: "#000000"
    readonly property color scrim: "#000000"
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
    readonly property color scrim: palette.scrim

    function withAlpha(color, alpha) {
        return Qt.rgba(color.r, color.g, color.b, alpha)
    }

    function toggleMode() {
        mode = isDark ? "light" : "dark"
    }
}
