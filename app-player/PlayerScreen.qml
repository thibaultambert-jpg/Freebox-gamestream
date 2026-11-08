// ============================================================
//  Écran de jeu : lecture du flux + capture des touches.
//
//  * Demande à l'agent de démarrer le flux (/api/stream/start),
//    puis lit l'URL retenue avec MediaPlayer + VideoOutput.
//  * Toutes les touches sont transmises au PC, sauf les touches
//    "pause" (Menu par défaut) et l'appui long sur Retour, qui
//    ouvrent le menu pause.
//  * Reconnexion automatique si le flux s'arrête ou se fige.
//  * "Resynchroniser" recharge le flux pour vider les tampons du
//    lecteur (la latence a tendance à dériver avec le temps).
// ============================================================
import QtQuick 2.0
import QtMultimedia 5.0
import "js/api.js" as Api
import "js/keys.js" as KeyMap

FocusScope {
    id: playerScreen

    property string url: ""
    property var urls: []
    property var pauseKeys: ["Menu"]
    property int backLongPressMs: 1500
    property real backDownAt: 0
    property bool paused: false
    property real startedAt: 0
    property real firstFrameMs: -1
    property int reconnects: 0
    property string lastKey: ""
    property real lastPlayingAt: 0
    property real lastPosition: -1

    Component.onCompleted: {
        Api.get("/api/app/config", function (status, cfg) {
            if (status === 200 && cfg) {
                pauseKeys = cfg.pause_keys || pauseKeys;
                backLongPressMs = cfg.back_long_press_ms !== undefined ? cfg.back_long_press_ms : backLongPressMs;
            }
        });
        startStream();
        input.start();
    }

    Component.onDestruction: {
        input.stop();
        Api.post("/api/stream/stop", {}, null);
    }

    // Demande le flux à l'agent puis lance la lecture
    function startStream() {
        info.text = "Démarrage du flux…";
        Api.post("/api/stream/start", {
            transport: store.get("transport"),
            resolution: store.get("resolution"),
            fps: store.get("fps"),
            bitrate_kbps: store.get("bitrate") * 1000,
            audio: store.get("audio")
        }, function (status, data) {
            if (status !== 200 || !data || !data.urls) {
                info.text = "Échec du démarrage : " + (data && data.error ? data.error : "agent injoignable");
                return;
            }
            urls = data.urls;
            var i = Math.min(store.get("urlIndex"), urls.length - 1);
            play(urls[i]);
        }, 8000);
    }

    function play(u) {
        url = u;
        startedAt = Api.now();
        firstFrameMs = -1;
        lastPosition = -1;
        player.stop();
        player.source = "";
        player.source = u;
        player.play();
        info.text = "";
    }

    // Recharge le lecteur (vide les tampons : rattrape le direct)
    function resync() {
        reconnects++;
        play(url);
    }

    function openPause() {
        paused = true;
        pauseMenu.currentIndex = 0;
        pauseMenu.forceActiveFocus();
    }

    function closePause() {
        paused = false;
        playerScreen.forceActiveFocus();
    }

    function isPauseKey(name) {
        return pauseKeys.indexOf(name) >= 0;
    }

    // ---------- vidéo ----------
    MediaPlayer {
        id: player
        autoPlay: true
        onHasVideoChanged: {
            if (hasVideo && firstFrameMs < 0) firstFrameMs = Api.now() - startedAt;
        }
        onPlaybackStateChanged: if (playbackState === MediaPlayer.PlayingState) lastPlayingAt = Api.now()
        onError: {
            info.text = "Erreur lecteur : " + errorString + " — nouvel essai…";
            root.later(1500, function () { if (!paused) resync(); });
        }
        onStatusChanged: {
            if (status === MediaPlayer.EndOfMedia || status === MediaPlayer.InvalidMedia) {
                root.later(1000, function () { if (!paused) resync(); });
            }
        }
    }

    VideoOutput {
        anchors.fill: parent
        source: player
        fillMode: VideoOutput.PreserveAspectFit
    }

    // Surveillance : si la position ne progresse plus pendant 4 s, on relance
    Timer {
        interval: 2000
        repeat: true
        running: !paused
        property int stuck: 0
        onTriggered: {
            if (player.playbackState !== MediaPlayer.PlayingState) { stuck++; }
            else if (player.position === lastPosition && player.position > 0) { stuck++; }
            else stuck = 0;
            lastPosition = player.position;
            if (stuck >= 2) { stuck = 0; resync(); }
        }
    }

    // Resynchronisation périodique optionnelle (réglage)
    Timer {
        interval: Math.max(1, store.get("autoResyncMin")) * 60000
        repeat: true
        running: store.get("autoResyncMin") > 0 && !paused
        onTriggered: resync()
    }

    InputSender { id: input }

    // ---------- touches ----------
    Keys.onPressed: {
        event.accepted = true;
        if (paused) return;   // touches remontées du menu pause : jamais transmises
        var name = KeyMap.nameOf(event.key);
        if (isPauseKey(name)) { if (!event.isAutoRepeat) openPause(); return; }
        if (name === "Back" && backLongPressMs > 0) {
            if (!event.isAutoRepeat) backDownAt = Api.now();
            else if (backDownAt > 0 && Api.now() - backDownAt >= backLongPressMs) {
                backDownAt = 0;
                input.send({ k: "Back", c: event.key, d: 0, r: 0 });
                openPause();
                return;
            }
        }
        lastKey = name;
        input.send(KeyMap.toEvent(event, true));
    }
    Keys.onReleased: {
        event.accepted = true;
        if (event.isAutoRepeat || paused) return;
        var name = KeyMap.nameOf(event.key);
        if (isPauseKey(name)) return;
        if (name === "Back") backDownAt = 0;
        input.send(KeyMap.toEvent(event, false));
    }

    // ---------- statistiques ----------
    Rectangle {
        visible: store.get("showStats") && !paused
        anchors.top: parent.top; anchors.right: parent.right
        anchors.margins: 24 * root.s
        width: statsText.width + 32 * root.s
        height: statsText.height + 20 * root.s
        radius: 10 * root.s
        color: "#99000000"
        Text {
            id: statsText
            anchors.centerIn: parent
            color: "#d8ffd8"
            font.pixelSize: 22 * root.s
            font.family: "monospace"
            text: "RTT " + (input.rtt >= 0 ? Math.round(input.rtt) + " ms" : "—")
                  + " • entrées " + input.mode
                  + " • 1re image " + (firstFrameMs >= 0 ? firstFrameMs + " ms" : "—")
                  + "\n" + store.get("transport") + " • " + store.get("resolution") + "@" + store.get("fps")
                  + " • " + store.get("bitrate") + " Mb/s • relances " + reconnects
                  + (lastKey ? " • touche " + lastKey : "")
        }
    }

    Text {
        id: info
        anchors.centerIn: parent
        color: "white"
        font.pixelSize: 36 * root.s
        style: Text.Outline; styleColor: "black"
    }

    // ---------- menu pause ----------
    Rectangle {
        anchors.fill: parent
        visible: paused
        color: "#cc05080d"
        Text {
            x: 120 * root.s; y: 100 * root.s
            text: "Pause"
            color: "white"; font.pixelSize: 64 * root.s; font.bold: true
        }
        Text {
            x: 120 * root.s; y: 190 * root.s
            text: "Le jeu continue sur le PC. Aucune touche n'est transmise pendant ce menu."
            color: "#8da2c0"; font.pixelSize: 28 * root.s
        }
        MenuList {
            id: pauseMenu
            s: root.s
            x: 120 * root.s; y: 280 * root.s
            model: [
                { label: "▶  Reprendre" },
                { label: "⟳  Resynchroniser le flux (réduit la latence)" },
                { label: "📊  Afficher / masquer les statistiques" },
                { label: "⏻  Quitter (arrête le flux)" }
            ]
            onActivated: {
                if (index === 0) closePause();
                else if (index === 1) { closePause(); resync(); }
                else if (index === 2) { store.set("showStats", !store.get("showStats")); closePause(); }
                else root.go("menu");
            }
            onOtherKey: {
                // Ignore la répétition de Retour encore maintenu après l'appui long
                if (event.isAutoRepeat) { event.accepted = true; return; }
                var name = KeyMap.nameOf(event.key);
                if (name === "Back" || isPauseKey(name)) { closePause(); event.accepted = true; }
            }
        }
    }
}
