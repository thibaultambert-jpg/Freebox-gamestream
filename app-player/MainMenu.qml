// ============================================================
//  Menu principal une fois connecté à un PC.
// ============================================================
import QtQuick 2.0

FocusScope {
    id: menu

    onActiveFocusChanged: if (activeFocus) list.forceActiveFocus()

    Text {
        id: title
        x: 120 * root.s; y: 80 * root.s
        text: root.serverName
        color: "white"; font.pixelSize: 64 * root.s; font.bold: true
    }
    Text {
        anchors.left: title.left; anchors.top: title.bottom
        text: root.serverHost + " • " + store.get("transport").toUpperCase() + " • "
              + store.get("resolution") + " @ " + store.get("fps") + " i/s • " + store.get("bitrate") + " Mb/s"
        color: "#8da2c0"; font.pixelSize: 30 * root.s
    }

    MenuList {
        id: list
        s: root.s
        x: 120 * root.s; y: 280 * root.s
        focus: true
        model: [
            { label: "▶  Jouer" },
            { label: "⚙  Réglages" },
            { label: "🧪  Sonde de compatibilité (Phase 0)" },
            { label: "⇄  Changer de PC" }
        ]
        onActivated: {
            if (index === 0) root.go("player");
            else if (index === 1) root.go("settings");
            else if (index === 2) root.go("probe");
            else root.go("home");
        }
        onOtherKey: {
            if (event.key === Qt.Key_Escape || event.key === Qt.Key_Back || event.key === Qt.Key_Backspace) {
                root.go("home");
                event.accepted = true;
            }
        }
    }

    Text {
        x: 120 * root.s
        anchors.bottom: parent.bottom; anchors.bottomMargin: 80 * root.s
        width: parent.width - 240 * root.s
        wrapMode: Text.WordWrap
        text: "Premier lancement ? Faites d'abord la sonde : elle teste les modules QML, les transports vidéo "
              + "et enregistre les codes de vos touches sur le PC (dossier agent-pc/probe-results)."
        color: "#56677f"; font.pixelSize: 26 * root.s
    }
}
