// ============================================================
//  Envoi des entrées (touches) vers l'agent PC.
//
//  1. WebSocket si le module QtWebSockets existe sur le Player
//     (connexion persistante = latence minimale) ;
//  2. sinon XMLHttpRequest POST /api/input, avec regroupement des
//     événements arrivés pendant qu'une requête est en cours.
//
//  Mesure aussi l'aller-retour réseau (rtt) toutes les 2 secondes.
// ============================================================
import QtQuick 2.0
import "js/api.js" as Api

Item {
    id: sender
    property var ws: null
    property bool wsOk: false
    property bool wsAvailable: true
    property var queue: []
    property bool inflight: false
    property real rtt: -1
    property string mode: "—"          // "WebSocket" | "HTTP"
    property int sent: 0
    property bool stopped: false

    function start() {
        stopped = false;
        mode = "HTTP";
        openWs();
    }

    function openWs() {
        if (!wsAvailable) return;
        try {
            if (ws) { ws.active = false; ws.destroy(); }
            ws = Qt.createQmlObject('import QtWebSockets 1.0; WebSocket { active: false }', sender, "ws");
        } catch (e) {
            console.log("QtWebSockets absent, repli HTTP : " + e);
            wsAvailable = false;
            ws = null;
            return;
        }
        ws.textMessageReceived.connect(function (msg) {
            try {
                var m = JSON.parse(msg);
                if (m.pong) rtt = Api.now() - m.pong;
            } catch (e) {}
        });
        ws.statusChanged.connect(function () {
            // 0 Connecting, 1 Open, 2 Closing, 3 Closed, 4 Error
            if (!ws) return;
            if (ws.status === 1) { wsOk = true; mode = "WebSocket"; }
            else if (ws.status >= 3) {
                wsOk = false; mode = "HTTP";
                root.later(3000, function () { if (!stopped && !wsOk) openWs(); });
            }
        });
        ws.url = "ws://" + Api.host + ":" + Api.port + "/ws?token=" + Api.token;
        ws.active = true;
    }

    function stop() {
        stopped = true; // empêche la reconnexion après arrêt
        if (ws) { var w = ws; ws = null; wsOk = false; w.active = false; w.destroy(); }
    }

    // Envoie un événement {k, c, d, r}
    function send(ev) {
        sent++;
        if (wsOk) {
            ws.sendTextMessage(JSON.stringify(ev));
            return;
        }
        var q = queue.slice();
        q.push(ev);
        queue = q;
        flush();
    }

    function flush() {
        if (inflight || !queue.length) return;
        var batch = queue;
        queue = [];
        inflight = true;
        Api.post("/api/input", { events: batch }, function () {
            inflight = false;
            flush();
        }, 2000);
    }

    // Mesure de l'aller-retour réseau
    Timer {
        interval: 2000
        repeat: true
        running: true
        triggeredOnStart: true
        onTriggered: {
            if (wsOk) {
                ws.sendTextMessage(JSON.stringify({ ping: Api.now() }));
            } else {
                var t0 = Api.now();
                Api.get("/api/ping", function (status) {
                    if (status === 200) rtt = Api.now() - t0;
                }, 1500);
            }
        }
    }
}
