// Zaod OS login theme. Original artwork and layout only.
import QtQuick 2.15
import QtQuick.Controls 2.15
import QtQuick.Layouts 1.15
import SddmComponents 2.0

Rectangle {
    id: root
    width: 1920
    height: 1080

    readonly property color accent: "#0067C0"
    readonly property color surface: "#1B1D21"
    readonly property color surfaceText: "#F6F7F9"
    readonly property int grid: 4

    function rounded(value) { return Math.round(value / grid) * grid }

    property int sessionIndex: sessionModel.lastIndex

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
            Layout.preferredHeight: rounded(160)
            radius: rounded(16)
            color: root.surface
            opacity: 0.92
            border.color: "#FFFFFF"
            border.width: 0
            ColumnLayout {
                anchors.fill: parent
                anchors.margins: rounded(24)
                spacing: rounded(16)

                // The account name is a field, not a label. Live media now asks
                // for a login like the installed system does, and on a fresh
                // live boot there is no "last user" to fall back on, so a label
                // reading "zaodlive" next to a password box could never sign in:
                // the login call had an empty user name.
                TextField {
                    id: userField
                    Layout.fillWidth: true
                    placeholderText: qsTr("User name")
                    text: userModel.lastUser || "zaodlive"
                    color: root.surfaceText
                    font { family: "Inter"; pixelSize: 16 }
                    selectByMouse: true
                    onAccepted: passwordField.forceActiveFocus()
                    KeyNavigation.tab: passwordField
                }

                TextField {
                    id: passwordField
                    Layout.fillWidth: true
                    placeholderText: qsTr("Password")
                    echoMode: TextInput.Password
                    font { family: "Inter"; pixelSize: 16 }
                    focus: true
                    selectByMouse: true
                    onAccepted: root.login()
                    KeyNavigation.backtab: userField
                    KeyNavigation.tab: sessionButton
                }

                RowLayout {
                    Layout.fillWidth: true
                    spacing: rounded(12)

                    Button {
                        id: sessionButton
                        text: sessionModel.getString(root.sessionIndex) || qsTr("Session")
                        font { family: "Inter"; pixelSize: 12 }
                        Layout.fillWidth: true
                        onClicked: root.sessionIndex = (root.sessionIndex + 1) % Math.max(1, sessionModel.rowCount())
                        KeyNavigation.tab: loginButton
                    }

                    Button {
                        id: loginButton
                        text: qsTr("Sign in")
                        font { family: "Inter"; pixelSize: 14; bold: true }
                        Layout.fillWidth: true
                        palette.button: root.accent
                        onClicked: root.login()
                    }
                }
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

        RowLayout {
            Layout.alignment: Qt.AlignHCenter
            spacing: rounded(8)

            Button {
                text: qsTr("Sleep")
                font { family: "Inter"; pixelSize: 12 }
                onClicked: sddm.suspend()
            }
            Button {
                text: qsTr("Restart")
                font { family: "Inter"; pixelSize: 12 }
                onClicked: sddm.reboot()
            }
            Button {
                text: qsTr("Shut down")
                font { family: "Inter"; pixelSize: 12 }
                onClicked: sddm.powerOff()
            }
        }
    }

    Text {
        id: clock
        anchors { top: parent.top; topMargin: rounded(48); horizontalCenter: parent.horizontalCenter }
        color: root.surfaceText
        opacity: 0.9
        font { family: "Inter"; pixelSize: 56; weight: Font.Light }
        text: Qt.formatTime(new Date(), config.timeFormat || "HH:mm")
    }

    Connections {
        target: sddm
        function onLoginFailed() {
            errorLabel.text = qsTr("Wrong password. Try again.")
            passwordField.text = ""
            passwordField.forceActiveFocus()
        }
        function onInformationMessage(message) {
            errorLabel.text = message
        }
    }

    Timer {
        interval: 1000
        running: true
        repeat: true
        onTriggered: clock.text = Qt.formatTime(new Date(), config.timeFormat || "HH:mm")
    }

    function login() {
        var user = userField.text.trim()
        if (user.length === 0) {
            errorLabel.text = qsTr("Enter the user name.")
            userField.forceActiveFocus()
            return
        }
        sddm.login(user, passwordField.text, root.sessionIndex)
    }

    Component.onCompleted: {
        if (userField.text.length > 0) {
            passwordField.forceActiveFocus()
        } else {
            userField.forceActiveFocus()
        }
    }
}
