// Zaod OS login theme. Original artwork and layout only.
//
// Built from Qt Quick primitives only - Rectangle, Text, TextInput, MouseArea -
// and deliberately from neither of the component modules. The greeter
// in this image rejected `Button.palette` and then `Button.contentItem` with
// "Cannot assign to non-existent property", which painted SDDM's red "The
// current theme cannot be loaded" banner over the login box on real hardware:
// `Button` and `TextField` in a theme resolve to those modules' simplified types,
// not to the Controls widgets that carry those properties. Nothing here shadows a
// Qt Quick type, so no property can go missing.
import QtQuick 2.15
import QtQuick.Layouts 1.15

Rectangle {
    id: root
    width: 1920
    height: 1080

    readonly property color accent: "#0067C0"
    readonly property color surface: "#1B1D21"
    readonly property color surfaceText: "#F6F7F9"
    readonly property color fieldSurface: "#24262B"
    readonly property color fieldText: "#F6F7F9"
    readonly property int grid: 4

    function rounded(value) { return Math.round(value / grid) * grid }

    property int sessionIndex: sessionModel.lastIndex

    function cycleSession() {
        var count = Math.max(1, sessionModel.rowCount())
        root.sessionIndex = (root.sessionIndex + 1) % count
    }

    function login() {
        errorLabel.text = ""
        sddm.login(userInput.text, passwordInput.text, root.sessionIndex)
    }

    Image {
        anchors.fill: parent
        source: config.background || "background.svg"
        fillMode: Image.PreserveAspectCrop
    }

    Rectangle {
        anchors.fill: parent
        color: "#0B1B2B"
        opacity: 0.25
    }

    ColumnLayout {
        anchors.centerIn: parent
        spacing: rounded(24)
        width: rounded(360)

        Text {
            text: "Zaod OS"
            color: root.surfaceText
            font { family: "Inter"; pixelSize: 32; letterSpacing: 1 }
            Layout.alignment: Qt.AlignHCenter
        }

        Rectangle {
            Layout.fillWidth: true
            Layout.preferredHeight: rounded(280)
            radius: rounded(16)
            color: root.surface
            opacity: 0.92

            ColumnLayout {
                anchors.fill: parent
                anchors.margins: rounded(24)
                spacing: rounded(12)

                // The account name is a field, not a label. Live media asks for a
                // login like the installed system does, and on a fresh live boot
                // there is no "last user" to fall back on, so a label reading
                // "zaodlive" next to a password box could never sign in.
                Rectangle {
                    id: userField
                    Layout.fillWidth: true
                    Layout.preferredHeight: rounded(44)
                    radius: rounded(10)
                    color: root.fieldSurface
                    border.width: 1
                    border.color: userInput.activeFocus ? root.accent : "#3A3D44"

                    Text {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.leftMargin: rounded(12)
                        anchors.rightMargin: rounded(12)
                        anchors.verticalCenter: parent.verticalCenter
                        text: qsTr("User name")
                        visible: userInput.text.length === 0
                        color: "#8B9098"
                        font { family: "Inter"; pixelSize: 14 }
                    }

                    TextInput {
                        id: userInput
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.leftMargin: rounded(12)
                        anchors.rightMargin: rounded(12)
                        anchors.verticalCenter: parent.verticalCenter
                        height: implicitHeight
                        color: root.fieldText
                        font { family: "Inter"; pixelSize: 15 }
                        selectByMouse: true
                        clip: true
                        text: userModel.lastUser || "zaodlive"
                        onAccepted: passwordInput.forceActiveFocus()
                        KeyNavigation.tab: passwordInput
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.IBeamCursor
                        onClicked: userInput.forceActiveFocus()
                    }
                }

                Rectangle {
                    id: passwordField
                    Layout.fillWidth: true
                    Layout.preferredHeight: rounded(44)
                    radius: rounded(10)
                    color: root.fieldSurface
                    border.width: 1
                    border.color: passwordInput.activeFocus ? root.accent : "#3A3D44"

                    Text {
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.leftMargin: rounded(12)
                        anchors.rightMargin: rounded(12)
                        anchors.verticalCenter: parent.verticalCenter
                        text: qsTr("Password")
                        visible: passwordInput.text.length === 0
                        color: "#8B9098"
                        font { family: "Inter"; pixelSize: 14 }
                    }

                    TextInput {
                        id: passwordInput
                        anchors.left: parent.left
                        anchors.right: parent.right
                        anchors.leftMargin: rounded(12)
                        anchors.rightMargin: rounded(12)
                        anchors.verticalCenter: parent.verticalCenter
                        height: implicitHeight
                        echoMode: TextInput.Password
                        color: root.fieldText
                        font { family: "Inter"; pixelSize: 15 }
                        selectByMouse: true
                        clip: true
                        onAccepted: root.login()
                        KeyNavigation.backtab: userInput
                        KeyNavigation.tab: sessionButton
                    }

                    MouseArea {
                        anchors.fill: parent
                        cursorShape: Qt.IBeamCursor
                        onClicked: passwordInput.forceActiveFocus()
                    }
                }

                // Session chooser: cycles the session list, as before, drawn from
                // primitives so it cannot fail to load.
                Rectangle {
                    id: sessionButton
                    Layout.fillWidth: true
                    Layout.preferredHeight: rounded(36)
                    radius: rounded(8)
                    color: sessionArea.containsMouse ? "#2E3138" : "#24262B"
                    border.width: 1
                    border.color: "#3A3D44"

                    Text {
                        anchors.centerIn: parent
                        text: sessionModel.getString(root.sessionIndex) || qsTr("Session")
                        color: root.surfaceText
                        font { family: "Inter"; pixelSize: 12 }
                    }

                    MouseArea {
                        id: sessionArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.cycleSession()
                    }
                }

                // Sign in: a filled rectangle and a label, with press and hover
                // feedback drawn by hand.
                Rectangle {
                    id: loginButton
                    Layout.fillWidth: true
                    Layout.preferredHeight: rounded(40)
                    radius: rounded(10)
                    color: loginArea.pressed ? Qt.darker(root.accent, 1.25)
                         : loginArea.containsMouse ? Qt.lighter(root.accent, 1.15)
                         : root.accent

                    Text {
                        anchors.centerIn: parent
                        text: qsTr("Sign in")
                        color: "#0B0F14"
                        font { family: "Inter"; pixelSize: 14; bold: true }
                    }

                    MouseArea {
                        id: loginArea
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.login()
                    }
                }

                Text {
                    id: errorLabel
                    text: ""
                    color: "#FFB4AB"
                    font { family: "Inter"; pixelSize: 12 }
                    Layout.alignment: Qt.AlignHCenter
                    visible: text.length > 0
                }
            }
        }
    }

    // Power controls, drawn the same primitive way.
    Row {
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.margins: rounded(24)
        spacing: rounded(12)

        Rectangle {
            width: rounded(96)
            height: rounded(32)
            radius: rounded(8)
            color: rebootArea.containsMouse ? "#2E3138" : root.surface
            opacity: 0.9

            Text {
                anchors.centerIn: parent
                text: qsTr("Restart")
                color: root.surfaceText
                font { family: "Inter"; pixelSize: 12 }
            }

            MouseArea {
                id: rebootArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: sddm.reboot()
            }
        }

        Rectangle {
            width: rounded(96)
            height: rounded(32)
            radius: rounded(8)
            color: powerArea.containsMouse ? "#2E3138" : root.surface
            opacity: 0.9

            Text {
                anchors.centerIn: parent
                text: qsTr("Shut down")
                color: root.surfaceText
                font { family: "Inter"; pixelSize: 12 }
            }

            MouseArea {
                id: powerArea
                anchors.fill: parent
                hoverEnabled: true
                cursorShape: Qt.PointingHandCursor
                onClicked: sddm.powerOff()
            }
        }
    }

    Connections {
        target: sddm
        function onLoginFailed() {
            errorLabel.text = qsTr("Wrong user name or password")
            passwordInput.text = ""
        }
    }

    Component.onCompleted: {
        passwordInput.forceActiveFocus()
    }
}
