// Zaod OS installer slideshow: three static panels, no network, no timers.
import QtQuick 2.15
import QtQuick.Controls 2.15

Item {
    id: root

    Presentation {
        anchors.fill: parent
        Slide {
            centeredText: qsTr("Zaod OS installs offline. Nothing is downloaded during setup.")
        }
        Slide {
            centeredText: qsTr("Applications install from the local repository as signed packages.")
        }
        Slide {
            centeredText: qsTr("Privacy defaults are yours: diagnostics stay off until you switch them on.")
        }
    }
}
