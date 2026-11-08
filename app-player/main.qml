// ============================================================
//  FreeStream – application Freebox Player (QML pur, sans C++)
//  Point d'entrée : gère la navigation entre les écrans.
//
//  Choix de compatibilité :
//   * imports QtQuick 2.x / QtMultimedia 5.x (Qt 5) ;
//   * JavaScript ES5 (var, function) ;
//   * aucun module optionnel importé statiquement : WebSocket et
//     LocalStorage sont chargés dynamiquement s'ils existent, pour
//     que l'app démarre même s'ils sont absents du Player.
// ============================================================
import QtQuick 2.0
import "js/api.js" as Api

Rectangle {
    id: root
    width: 1920
    height: 1080
    color: "#0b0f17"
    focus: true

    // Facteur d'échelle : l'interface est dessinée pour du 1080p
    property real s: height / 1080
    property string screen: "home"   // home | menu | settings | probe | player

    // Serveur (agent PC) sélectionné
    property string serverHost: ""
    property int serverPort: 8765
    property string serverName: ""

    // ---------- utilitaires partagés ----------

    // Équivalent de setTimeout (absent en QML) : crée un Timer à usage unique
    function later(ms, fn) {
        var t = Qt.createQmlObject('import QtQuick 2.0; Timer { repeat: false }', root, "later");
        t.interval = ms;
        t.triggered.connect(function () { t.destroy(); fn(); });
        t.start();
        return t;
    }

    function go(name) {
        screen = name;
    }

    // Donne le focus clavier à l'écran affiché
    onScreenChanged: {
        if (screen === "home") home.forceActiveFocus();
        else if (screen === "menu") menu.forceActiveFocus();
        else if (screen === "settings") settings.forceActiveFocus();
        // probe / player : le Loader donne le focus à l'écran chargé
    }

    function toast(msg) {
        toastText.text = msg;
        toastBox.opacity = 1;
        toastTimer.restart();
    }

    Component.onCompleted: {
        Api.init(later);
        store.load();
        home.refresh();
        home.forceActiveFocus();
    }

    // Stockage persistant (LocalStorage si disponible)
    Store { id: store }

    // ---------- écrans ----------
    HomeScreen {
        id: home
        anchors.fill: parent
        visible: root.screen === "home"
        focus: visible
    }

    MainMenu {
        id: menu
        anchors.fill: parent
        visible: root.screen === "menu"
        focus: visible
    }

    SettingsScreen {
        id: settings
        anchors.fill: parent
        visible: root.screen === "settings"
        focus: visible
    }

    // Les écrans vidéo ne sont instanciés que lorsqu'ils sont affichés
    // (libère le décodeur matériel quand on les quitte).
    Loader {
        anchors.fill: parent
        active: root.screen === "probe"
        source: "ProbeScreen.qml"
        focus: active
        onLoaded: item.forceActiveFocus()
    }

    Loader {
        anchors.fill: parent
        active: root.screen === "player"
        source: "PlayerScreen.qml"
        focus: active
        onLoaded: item.forceActiveFocus()
    }

    // ---------- notification temporaire ----------
    Rectangle {
        id: toastBox
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 60 * root.s
        width: toastText.width + 60 * root.s
        height: toastText.height + 30 * root.s
        radius: 12 * root.s
        color: "#cc1d2633"
        opacity: 0
        z: 100
        Behavior on opacity { NumberAnimation { duration: 200 } }
        Text {
            id: toastText
            anchors.centerIn: parent
            color: "white"
            font.pixelSize: 30 * root.s
        }
        Timer { id: toastTimer; interval: 3000; onTriggered: toastBox.opacity = 0 }
    }
}
