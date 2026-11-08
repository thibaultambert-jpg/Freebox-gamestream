// ============================================================
//  Stockage persistant clé/valeur (JSON).
//  Utilise QtQuick.LocalStorage s'il existe sur le Player ;
//  sinon, garde les valeurs en mémoire (perdues à la fermeture).
//  Le module est chargé dynamiquement pour ne pas empêcher
//  l'app de démarrer s'il est absent.
// ============================================================
import QtQuick 2.0

QtObject {
    id: store

    property var db: null
    property bool persistent: false
    property var values: ({})

    // Valeurs par défaut des réglages
    property var defaults: ({
        "servers": [],            // [{host, port, name, token}]
        "lastHost": "",
        "transport": "udp",
        "urlIndex": 0,            // variante d'URL retenue par la sonde
        "resolution": "1280x720",
        "fps": 60,
        "bitrate": 12,            // Mb/s
        "audio": false,
        "showStats": true,
        "autoResyncMin": 0        // resynchronisation périodique (0 = jamais)
    })

    function load() {
        try {
            var helper = Qt.createQmlObject(
                'import QtQuick 2.0; import QtQuick.LocalStorage 2.0 as LS; QtObject {' +
                ' function open() { return LS.LocalStorage.openDatabaseSync("FreeStream", "1.0", "FreeStream", 100000); } }',
                store, "storage");
            db = helper.open();
            db.transaction(function (tx) {
                tx.executeSql("CREATE TABLE IF NOT EXISTS kv (k TEXT PRIMARY KEY, v TEXT)");
                var rs = tx.executeSql("SELECT k, v FROM kv");
                var d = {};
                for (var i = 0; i < rs.rows.length; i++) {
                    try { d[rs.rows.item(i).k] = JSON.parse(rs.rows.item(i).v); } catch (e) {}
                }
                values = d;
            });
            persistent = true;
        } catch (err) {
            console.log("LocalStorage indisponible, réglages en mémoire : " + err);
            persistent = false;
        }
    }

    function get(key) {
        if (values[key] !== undefined) return values[key];
        return defaults[key];
    }

    function set(key, value) {
        // Nouvel objet à chaque écriture : déclenche la mise à jour des liaisons QML
        var d = {};
        for (var k in values) d[k] = values[k];
        d[key] = value;
        values = d;
        if (!db) return;
        try {
            db.transaction(function (tx) {
                tx.executeSql("INSERT OR REPLACE INTO kv (k, v) VALUES (?, ?)", [key, JSON.stringify(value)]);
            });
        } catch (err) {
            console.log("Écriture impossible : " + err);
        }
    }

    // ---- gestion de la liste des PC ----
    function servers() {
        return get("servers") || [];
    }

    function saveServer(host, port, name, token) {
        var list = servers().slice();
        var found = false;
        for (var i = 0; i < list.length; i++) {
            if (list[i].host === host && list[i].port === port) {
                list[i].name = name || list[i].name;
                if (token !== undefined) list[i].token = token;
                found = true;
            }
        }
        if (!found) list.push({ host: host, port: port, name: name || host, token: token || "" });
        set("servers", list);
        set("lastHost", host);
    }

    function forgetServer(host, port) {
        var list = servers().filter(function (x) { return !(x.host === host && x.port === port); });
        set("servers", list);
    }

    function tokenFor(host, port) {
        var list = servers();
        for (var i = 0; i < list.length; i++)
            if (list[i].host === host && list[i].port === port) return list[i].token || "";
        return "";
    }
}
