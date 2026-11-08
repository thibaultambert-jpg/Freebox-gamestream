// ============================================================
//  Sonde de compatibilité – PHASE 0 (go / no-go)
//
//  Répond automatiquement aux questions bloquantes du plan :
//   1. Quels modules QML existent sur le Player ? (WebSocket,
//      LocalStorage, Gamepad, QtMultimedia…)
//   2. Quel est l'aller-retour réseau HTTP vers le PC ?
//   3. Quels transports vidéo le lecteur sait-il lire, avec quelle
//      syntaxe d'URL, et en combien de temps s'affiche la 1re image ?
//   4. Quels codes envoient les touches de la télécommande / manette ?
//
//  Le rapport complet est envoyé à l'agent, qui l'enregistre dans
//  agent-pc/probe-results/. Le meilleur transport est mémorisé.
// ============================================================
import QtQuick 2.0
import QtMultimedia 5.0
import "js/api.js" as Api
import "js/keys.js" as KeyMap

FocusScope {
    id: probe

    property var report: ({ env: {}, modules: [], rtt: {}, video: [], variants: [], keys: [] })
    property var steps: []
    property var probeCfg: null
    property string phase: "auto"      // auto | keys | done
    property var current: null         // test vidéo en cours
    property real backDownAt: 0
    property int timeoutS: 12

    function log(line) {
        logModel.append({ line: line });
        logView.positionViewAtEnd();
    }

    function runNext() {
        var queue = steps;
        if (!queue.length) return;
        var s = queue.shift();
        steps = queue;
        s();
    }

    Component.onCompleted: {
        log("Sonde FreeStream — " + root.serverName + " (" + root.serverHost + ")");
        Api.get("/api/probe/config", function (status, cfg) {
            if (status !== 200 || !cfg) { log("❌ Agent injoignable"); return; }
            probeCfg = cfg;
            timeoutS = cfg.timeout_s || 12;
            buildSteps();
            runNext();
        });
    }

    Component.onDestruction: {
        Api.post("/api/stream/stop", {}, null);
    }

    function buildSteps() {
        steps = [stepEnv, stepModules, stepRtt];
        var tr = probeCfg.transports;
        for (var i = 0; i < tr.length; i++)
            steps.push(makeTransportStep(tr[i]));
        steps.push(stepVariants);
        steps.push(stepKeys);
    }

    // ---------- 1. environnement ----------
    function stepEnv() {
        var env = { os: Qt.platform.os, appWidth: root.width, appHeight: root.height,
                    date: new Date().toString() };
        try {
            var sc = Qt.createQmlObject('import QtQuick 2.0; import QtQuick.Window 2.2; QtObject {' +
                ' property int w: Screen.width; property int h: Screen.height; property real dpr: Screen.devicePixelRatio }',
                probe, "screen");
            env.screen = sc.w + "x" + sc.h + " (dpr " + sc.dpr + ")";
        } catch (e) { env.screen = "inconnu"; }
        report.env = env;
        log("Plateforme : " + env.os + " • écran " + env.screen + " • app " + env.appWidth + "x" + env.appHeight);
        runNext();
    }

    // ---------- 2. modules QML ----------
    function stepModules() {
        var mods = probeCfg.modules;
        var res = [];
        for (var i = 0; i < mods.length; i++) {
            var ok = true, err = "";
            try {
                var o = Qt.createQmlObject('import QtQml 2.0; import ' + mods[i] + '; QtObject {}', probe, "mod" + i);
                o.destroy();
            } catch (e) {
                ok = false;
                err = e.qmlErrors && e.qmlErrors.length ? e.qmlErrors[0].message : String(e);
            }
            res.push({ module: mods[i], ok: ok, error: err });
            log((ok ? "✅ " : "❌ ") + mods[i] + (ok ? "" : "  (" + err + ")"));
        }
        report.modules = res;
        runNext();
    }

    // ---------- 3. aller-retour HTTP ----------
    function stepRtt() {
        var samples = [];
        function ping(n) {
            if (n === 0) {
                report.rtt = { median_ms: Api.median(samples), samples: samples };
                log("Aller-retour HTTP médian : " + Api.median(samples) + " ms (" + samples.join(", ") + ")");
                runNext();
                return;
            }
            var t0 = Api.now();
            Api.get("/api/ping", function (status) {
                if (status === 200) samples.push(Api.now() - t0);
                ping(n - 1);
            }, 2000);
        }
        ping(10);
    }

    // ---------- 4. transports vidéo ----------
    function makeTransportStep(transport) {
        return function () {
            log("— Transport " + transport + " : démarrage de la mire sur le PC…");
            Api.post("/api/stream/start", { transport: transport, source: "testsrc",
                                            resolution: "1280x720", fps: 30, bitrate_kbps: 6000 },
                function (status, data) {
                    if (status !== 200 || !data) {
                        log("❌ L'agent refuse : " + (data && data.error ? data.error : status));
                        report.video.push({ transport: transport, ok: false, error: "agent" });
                        runNext();
                        return;
                    }
                    var urls = data.urls;
                    var idx = 0;
                    function nextUrl() {
                        if (idx >= urls.length) { runNext(); return; }
                        var u = urls[idx];
                        var ui = idx;
                        idx++;
                        testUrl(transport, u, ui, nextUrl);
                    }
                    root.later(1000, nextUrl);  // laisse FFmpeg démarrer
                }, 10000);
        };
    }

    // Lit une URL et observe le lecteur jusqu'au succès ou au délai max
    function testUrl(transport, u, urlIndex, done, extra) {
        log("   essai " + u);
        current = { transport: transport, url: u, urlIndex: urlIndex, ok: false, first_video_ms: -1,
                    error: "", statuses: [], t0: Api.now(), done: done, extra: extra || null, finished: false };
        probePlayer.stop();
        probePlayer.source = "";
        probePlayer.source = u;
        probePlayer.play();
        var test = current;
        root.later(timeoutS * 1000, function () { finishTest(test, false, "délai dépassé"); });
    }

    function noteStatus(what) {
        if (!current || current.finished) return;
        current.statuses.push({ t: Api.now() - current.t0, what: what });
    }

    function finishTest(test, ok, err) {
        if (!test || test.finished) return;
        test.finished = true;
        test.ok = ok;
        if (err) test.error = err;
        var rec = { transport: test.transport, url: test.url, url_index: test.urlIndex, ok: test.ok,
                    first_video_ms: test.first_video_ms, error: test.error, statuses: test.statuses };
        if (test.extra) {
            rec.variant = test.extra;
            report.variants.push(rec);
        } else {
            report.video.push(rec);
        }
        log((ok ? "   ✅ image en " + test.first_video_ms + " ms" : "   ❌ " + test.error));
        probePlayer.stop();
        probePlayer.source = "";
        current = null;
        root.later(500, test.done);
    }

    MediaPlayer {
        id: probePlayer
        autoPlay: true
        onStatusChanged: noteStatus("status=" + status)
        onPlaybackStateChanged: noteStatus("state=" + playbackState)
        onError: {
            noteStatus("error=" + errorString);
            if (current) finishTest(current, false, errorString);
        }
        onHasVideoChanged: {
            noteStatus("hasVideo=" + hasVideo);
            if (hasVideo && current && current.first_video_ms < 0) {
                current.first_video_ms = Api.now() - current.t0;
                var test = current;
                // Succès si la lecture tient 2 secondes de plus sans erreur
                root.later(2000, function () {
                    if (!test.finished && probePlayer.playbackState === MediaPlayer.PlayingState)
                        finishTest(test, true, "");
                });
            }
        }
    }

    // ---------- 5. variantes (1080p60, HEVC) sur le meilleur transport ----------
    function bestVideo() {
        var order = ["udp", "rtp", "udp-multicast", "rtp-multicast", "http"];
        var best = null;
        for (var i = 0; i < report.video.length; i++) {
            var v = report.video[i];
            if (!v.ok) continue;
            if (!best || order.indexOf(v.transport) < order.indexOf(best.transport)
                || (v.transport === best.transport && v.first_video_ms < best.first_video_ms))
                best = v;
        }
        return best;
    }

    function stepVariants() {
        var best = bestVideo();
        if (!best) { log("Aucun transport ne fonctionne : variantes ignorées."); runNext(); return; }
        var variants = [
            { resolution: "1920x1080", fps: 60, bitrate_kbps: 15000 },
            { resolution: "1280x720", fps: 60, bitrate_kbps: 8000, codec: "hevc" }
        ];
        function nextVariant() {
            if (!variants.length) { runNext(); return; }
            var v = variants.shift();
            log("— Variante " + JSON.stringify(v) + " sur " + best.transport);
            var body = { transport: best.transport, source: "testsrc" };
            for (var k in v) body[k] = v[k];
            Api.post("/api/stream/start", body, function (status, data) {
                if (status !== 200 || !data) { nextVariant(); return; }
                root.later(1000, function () {
                    testUrl(best.transport, data.urls[best.url_index], best.url_index, nextVariant, v);
                });
            }, 10000);
        }
        nextVariant();
    }

    // ---------- 6. journal des touches ----------
    function stepKeys() {
        Api.post("/api/stream/stop", {}, null);
        phase = "keys";
        log("— Appuyez sur TOUTES les touches de la télécommande et de la manette.");
        log("  Maintenez RETOUR 3 secondes pour terminer.");
    }

    function finish() {
        phase = "done";
        var best = bestVideo();
        if (best) {
            report.best = { transport: best.transport, url_index: best.url_index, url: best.url,
                            first_video_ms: best.first_video_ms };
            store.set("transport", best.transport);
            store.set("urlIndex", best.url_index);
            log("🏁 Meilleur transport : " + best.transport + " (" + best.url + ") — enregistré dans les réglages.");
        } else {
            report.best = null;
            log("🏁 Aucun transport vidéo n'a fonctionné : voir le rapport (plan B dans docs/ANALYSE.md).");
        }
        Api.post("/api/probe/report", report, function (status, data) {
            log(status === 200 ? "Rapport enregistré sur le PC : probe-results/" + data.saved
                               : "⚠ Envoi du rapport impossible");
            log("Retour : revenir au menu.");
        }, 10000);
    }

    Keys.onPressed: {
        event.accepted = true;
        var name = KeyMap.nameOf(event.key);
        if (phase === "keys") {
            if (name === "Back") {
                if (!event.isAutoRepeat) backDownAt = Api.now();
                else if (backDownAt > 0 && Api.now() - backDownAt > 3000) { backDownAt = 0; finish(); return; }
            }
            if (!event.isAutoRepeat) {
                var k = { k: name, c: event.key, hex: "0x" + event.key.toString(16), text: event.text,
                          modifiers: event.modifiers, native_scan_code: event.nativeScanCode };
                report.keys.push(k);
                Api.post("/api/probe/key", k, null);
                log("   touche " + name + "  code=" + event.key + " (" + k.hex + ")  texte=\"" + event.text + "\"  scan=" + event.nativeScanCode);
            } else {
                // On note qu'une répétition existe pour cette touche (utile pour l'agent)
                var last = report.keys.length ? report.keys[report.keys.length - 1] : null;
                if (last && last.c === event.key) last.repeats = true;
            }
        } else if (phase === "done" && (name === "Back")) {
            root.go("menu");
        } else if (phase === "auto" && name === "Back") {
            root.go("menu");   // abandon de la sonde
        }
    }
    Keys.onReleased: {
        if (phase === "keys" && !event.isAutoRepeat) {
            var name = KeyMap.nameOf(event.key);
            if (name === "Back") backDownAt = 0;
            // Vérifie que le relâchement arrive bien (sinon l'agent relâche par délai)
            for (var i = report.keys.length - 1; i >= 0; i--)
                if (report.keys[i].c === event.key) { report.keys[i].release_seen = true; break; }
        }
        event.accepted = true;
    }

    // ---------- interface ----------
    Text {
        x: 60 * root.s; y: 40 * root.s
        text: "Sonde de compatibilité (Phase 0)"
        color: "white"; font.pixelSize: 48 * root.s; font.bold: true
    }

    ListModel { id: logModel }

    ListView {
        id: logView
        x: 60 * root.s; y: 120 * root.s
        width: 1100 * root.s
        height: parent.height - 180 * root.s
        clip: true
        model: logModel
        delegate: Text {
            width: logView.width
            wrapMode: Text.WrapAnywhere
            text: line
            color: "#d6e2f5"
            font.pixelSize: 22 * root.s
            font.family: "monospace"
        }
    }

    Rectangle {
        x: 1200 * root.s; y: 120 * root.s
        width: 680 * root.s; height: 383 * root.s
        color: "black"
        border.color: "#2b3a52"; border.width: 2
        VideoOutput {
            anchors.fill: parent
            anchors.margins: 2
            source: probePlayer
        }
        Text {
            anchors.top: parent.bottom; anchors.topMargin: 10 * root.s
            text: current ? "Lecture : " + current.url : "Aperçu vidéo"
            color: "#8da2c0"; font.pixelSize: 22 * root.s
            width: parent.width; elide: Text.ElideMiddle
        }
    }
}
