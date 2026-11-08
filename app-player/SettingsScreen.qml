// ============================================================
//  Réglages du flux (stockés sur le Player).
//  ◀ ▶ changent la valeur ; OK ou Retour enregistrent et reviennent.
// ============================================================
import QtQuick 2.0
import "js/api.js" as Api

FocusScope {
    id: settings

    // Valeurs possibles de chaque réglage
    property var transports: ["udp", "rtp", "udp-multicast", "rtp-multicast", "http"]
    property var resolutions: ["1280x720", "1600x900", "1920x1080", "native"]
    property var fpsList: [30, 60]
    property var bitrates: [4, 6, 8, 10, 12, 15, 20, 25, 30, 40]
    property var resyncList: [0, 5, 10, 20]
    property var profiles: []
    property string profile: ""

    function cycle(arr, value, delta) {
        var i = arr.indexOf(value);
        if (i < 0) i = 0;
        return arr[(i + delta + arr.length) % arr.length];
    }

    function rebuild() {
        list.model = [
            { label: "Transport vidéo", value: store.get("transport") },
            { label: "Variante d'URL", value: "n°" + store.get("urlIndex") },
            { label: "Résolution", value: store.get("resolution") },
            { label: "Images par seconde", value: store.get("fps") },
            { label: "Débit", value: store.get("bitrate") + " Mb/s" },
            { label: "Audio (dans le flux)", value: store.get("audio") ? "oui" : "non" },
            { label: "Statistiques à l'écran", value: store.get("showStats") ? "oui" : "non" },
            { label: "Resynchronisation auto", value: store.get("autoResyncMin") ? "toutes les " + store.get("autoResyncMin") + " min" : "jamais" },
            { label: "Profil de touches (PC)", value: profile || "—" }
        ];
    }

    onActiveFocusChanged: {
        if (!activeFocus) return;
        var keep = list.currentIndex;
        rebuild();
        list.currentIndex = keep;
        list.forceActiveFocus();
        // Profils de mapping disponibles sur l'agent
        Api.get("/api/app/config", function (status, cfg) {
            if (status === 200 && cfg) {
                profiles = cfg.profiles; profile = cfg.profile;
                var k = list.currentIndex; rebuild(); list.currentIndex = k;
            }
        });
    }

    Text {
        x: 120 * root.s; y: 80 * root.s
        text: "Réglages"
        color: "white"; font.pixelSize: 64 * root.s; font.bold: true
    }

    MenuList {
        id: list
        s: root.s
        x: 120 * root.s; y: 220 * root.s
        width: 1300 * root.s
        rowHeight: 76 * root.s
        focus: true
        onChanged: {
            var d = delta;
            if (index === 0) { store.set("transport", cycle(transports, store.get("transport"), d)); store.set("urlIndex", 0); }
            else if (index === 1) store.set("urlIndex", (store.get("urlIndex") + d + 3) % 3);
            else if (index === 2) store.set("resolution", cycle(resolutions, store.get("resolution"), d));
            else if (index === 3) store.set("fps", cycle(fpsList, store.get("fps"), d));
            else if (index === 4) store.set("bitrate", cycle(bitrates, store.get("bitrate"), d));
            else if (index === 5) store.set("audio", !store.get("audio"));
            else if (index === 6) store.set("showStats", !store.get("showStats"));
            else if (index === 7) store.set("autoResyncMin", cycle(resyncList, store.get("autoResyncMin"), d));
            else if (index === 8 && profiles.length) {
                var p = cycle(profiles, profile, d);
                Api.post("/api/profile", { profile: p }, function (status) {
                    if (status === 200) { profile = p; var k = list.currentIndex; rebuild(); list.currentIndex = k; }
                });
            }
            var keep = list.currentIndex;
            rebuild();
            list.currentIndex = keep;
        }
        onActivated: root.go("menu")
        onOtherKey: {
            if (event.key === Qt.Key_Escape || event.key === Qt.Key_Back || event.key === Qt.Key_Backspace) {
                root.go("menu");
                event.accepted = true;
            }
        }
    }

    Text {
        x: 120 * root.s
        anchors.bottom: parent.bottom; anchors.bottomMargin: 80 * root.s
        width: parent.width - 240 * root.s
        wrapMode: Text.WordWrap
        text: "La sonde (Phase 0) règle automatiquement le transport et la variante d'URL qui fonctionnent. "
              + "En 1080p, montez le débit à 15–20 Mb/s ; en Wi-Fi, préférez 720p et 8–10 Mb/s."
        color: "#56677f"; font.pixelSize: 26 * root.s
    }
}
