// ============================================================
//  Écran d'accueil : choix du PC, saisie d'IP, scan du réseau,
//  appairage par code PIN.
//
//  Pas de mDNS en QML pur : on propose (1) la saisie de l'IP avec
//  les chiffres de la télécommande, (2) un scan HTTP du sous-réseau
//  (requêtes /api/info sur les 254 adresses, par paquets).
// ============================================================
import QtQuick 2.0
import "js/api.js" as Api

FocusScope {
    id: home
    objectName: "homeScreen"
    property string mode: "list"    // list | ip | pin | scan
    property var octets: [192, 168, 1, 10]
    property int octetIndex: 3
    property string typed: ""       // chiffres tapés pour l'octet courant
    property string pin: ""
    property string pendingHost: ""
    property int pendingPort: 8765
    property string pendingName: ""
    property var found: []
    property int scanDone: 0
    property bool scanning: false

    function entries() {
        var list = store.servers();
        var m = [];
        for (var i = 0; i < list.length; i++)
            m.push({ label: list[i].name + "  (" + list[i].host + ")", value: undefined });
        m.push({ label: "＋ Ajouter un PC par son adresse IP", value: undefined });
        m.push({ label: "🔍 Rechercher les PC sur le réseau", value: undefined });
        return m;
    }

    function refresh() {
        // Préremplit l'IP avec celle du dernier PC utilisé
        var last = store.get("lastHost");
        if (last && last.split(".").length === 4) {
            var p = last.split(".");
            octets = [parseInt(p[0], 10), parseInt(p[1], 10), parseInt(p[2], 10), parseInt(p[3], 10)];
        }
        menuList.model = entries();
        menuList.currentIndex = 0;
    }

    onVisibleChanged: if (visible) { mode = "list"; refresh(); menuList.forceActiveFocus(); }
    Component.onCompleted: refresh()

    // Contacte un PC : s'il a déjà un jeton valide, on va au menu ; sinon PIN.
    function connectTo(host, port) {
        Api.setServer(host, port, store.tokenFor(host, port));
        statusText.text = "Connexion à " + host + "…";
        Api.get("/api/info", function (status, info) {
            if (status !== 200 || !info || info.app !== "freestream") {
                statusText.text = "Aucun agent FreeStream sur " + host + ":" + port;
                return;
            }
            pendingHost = host; pendingPort = port; pendingName = info.name;
            if (!info.require_pin) { enter(host, port, info.name, ""); return; }
            // Vérifie que le jeton mémorisé est toujours accepté
            Api.get("/api/app/config", function (st2) {
                if (st2 === 200) enter(host, port, info.name, Api.token);
                else { pin = ""; mode = "pin"; pinBox.forceActiveFocus(); statusText.text = ""; }
            });
        }, 3000);
    }

    function enter(host, port, name, token) {
        store.saveServer(host, port, name, token);
        Api.setServer(host, port, token);
        root.serverHost = host; root.serverPort = port; root.serverName = name;
        statusText.text = "";
        root.go("menu");
    }

    function submitPin() {
        Api.setServer(pendingHost, pendingPort, "");
        Api.post("/api/pair", { pin: pin }, function (status, data) {
            if (status === 200 && data && data.token) {
                enter(pendingHost, pendingPort, pendingName, data.token);
            } else {
                pin = "";
                statusText.text = data && data.error ? data.error : "Échec de l'appairage";
            }
        });
    }

    // Scan du /24 : 254 requêtes, 24 en parallèle, délai 1,2 s
    function startScan() {
        mode = "scan"; scanning = true; found = []; scanDone = 0;
        scanBox.forceActiveFocus();
        var prefix = octets[0] + "." + octets[1] + "." + octets[2] + ".";
        var next = 1, inFlight = 0;
        function launch() {
            while (inFlight < 24 && next <= 254 && scanning) {
                (function (ip) {
                    inFlight++;
                    Api.getUrl("http://" + ip + ":8765/api/info", function (status, info) {
                        inFlight--; scanDone++;
                        if (status === 200 && info && info.app === "freestream") {
                            var f = found.slice();
                            f.push({ host: ip, name: info.name });
                            found = f;
                        }
                        if (next <= 254) launch();
                        else if (inFlight === 0) scanning = false;
                    }, 1200);
                })(prefix + next);
                next++;
            }
        }
        launch();
    }

    Text {
        id: title
        x: 120 * root.s; y: 80 * root.s
        text: "FreeStream"
        color: "white"
        font.pixelSize: 72 * root.s
        font.bold: true
    }
    Text {
        anchors.left: title.left
        anchors.top: title.bottom
        text: "Jouez aux jeux de votre PC sur le Freebox Player"
        color: "#8da2c0"
        font.pixelSize: 30 * root.s
    }

    // ---------- liste des PC ----------
    MenuList {
        id: menuList
        visible: home.mode === "list"
        focus: home.mode === "list"
        s: root.s
        x: 120 * root.s; y: 260 * root.s
        width: 1100 * root.s
        onActivated: {
            var list = store.servers();
            if (index < list.length) connectTo(list[index].host, list[index].port);
            else if (index === list.length) { typed = ""; octetIndex = 0; mode = "ip"; ipBox.forceActiveFocus(); }
            else startScan();
        }
        onOtherKey: {
            // Touche rouge : oublier le PC sélectionné
            if (event.key === Qt.Key_Red) {
                var list = store.servers();
                if (currentIndex < list.length) {
                    store.forgetServer(list[currentIndex].host, list[currentIndex].port);
                    refresh();
                    root.toast("PC oublié");
                }
                event.accepted = true;
            }
        }
    }

    // ---------- saisie de l'adresse IP ----------
    FocusScope {
        id: ipBox
        visible: home.mode === "ip"
        x: 120 * root.s; y: 260 * root.s
        width: 1400 * root.s; height: 400 * root.s

        Text {
            text: "Adresse IP du PC (affichée dans la console de l'agent)"
            color: "white"; font.pixelSize: 36 * root.s
        }
        Row {
            y: 80 * root.s
            spacing: 20 * root.s
            Repeater {
                model: 4
                Rectangle {
                    width: 180 * root.s; height: 120 * root.s; radius: 12 * root.s
                    color: index === home.octetIndex ? "#2b6cff" : "#1a2230"
                    Text {
                        anchors.centerIn: parent
                        text: index === home.octetIndex && home.typed !== "" ? home.typed : home.octets[index]
                        color: "white"; font.pixelSize: 60 * root.s
                    }
                }
            }
        }
        Text {
            y: 240 * root.s
            text: "Chiffres : saisir • ◀ ▶ : changer de nombre • ▲ ▼ : +1/−1 • OK : valider • Retour : annuler"
            color: "#8da2c0"; font.pixelSize: 28 * root.s
        }

        function commitTyped() {
            if (typed === "") return;
            var o = octets.slice();
            o[octetIndex] = Math.min(255, parseInt(typed, 10));
            octets = o; typed = "";
        }

        Keys.onPressed: {
            var k = event.key;
            event.accepted = true;
            if (k >= Qt.Key_0 && k <= Qt.Key_9) {
                typed = (typed + String(k - Qt.Key_0)).slice(-3);
                if (typed.length === 3 && octetIndex < 3) { commitTyped(); octetIndex++; }
            } else if (k === Qt.Key_Left) { commitTyped(); octetIndex = Math.max(0, octetIndex - 1); }
            else if (k === Qt.Key_Right) { commitTyped(); octetIndex = Math.min(3, octetIndex + 1); }
            else if (k === Qt.Key_Up || k === Qt.Key_Down) {
                commitTyped();
                var o = octets.slice();
                o[octetIndex] = (o[octetIndex] + (k === Qt.Key_Up ? 1 : 255)) % 256;
                octets = o;
            } else if (k === Qt.Key_Return || k === Qt.Key_Enter || k === Qt.Key_Select) {
                commitTyped();
                mode = "list"; menuList.forceActiveFocus();
                connectTo(octets.join("."), 8765);
            } else if (k === Qt.Key_Escape || k === Qt.Key_Back || k === Qt.Key_Backspace) {
                mode = "list"; menuList.forceActiveFocus();
            } else event.accepted = false;
        }
    }

    // ---------- code PIN ----------
    FocusScope {
        id: pinBox
        visible: home.mode === "pin"
        x: 120 * root.s; y: 260 * root.s
        width: 1400 * root.s; height: 400 * root.s
        Text {
            text: "Code PIN affiché dans la console de l'agent sur « " + home.pendingName + " »"
            color: "white"; font.pixelSize: 36 * root.s
        }
        Row {
            y: 80 * root.s
            spacing: 20 * root.s
            Repeater {
                model: 4
                Rectangle {
                    width: 120 * root.s; height: 140 * root.s; radius: 12 * root.s
                    color: "#1a2230"
                    border.color: index === home.pin.length ? "#5d8cff" : "transparent"
                    border.width: 3 * root.s
                    Text {
                        anchors.centerIn: parent
                        text: index < home.pin.length ? "•" : ""
                        color: "white"; font.pixelSize: 80 * root.s
                    }
                }
            }
        }
        Keys.onPressed: {
            var k = event.key;
            event.accepted = true;
            if (k >= Qt.Key_0 && k <= Qt.Key_9) {
                pin = pin + String(k - Qt.Key_0);
                if (pin.length === 4) submitPin();
            } else if (k === Qt.Key_Left || k === Qt.Key_Backspace) {
                pin = pin.slice(0, -1);
            } else if (k === Qt.Key_Escape || k === Qt.Key_Back) {
                mode = "list"; menuList.forceActiveFocus();
            } else event.accepted = false;
        }
    }

    // ---------- scan ----------
    FocusScope {
        id: scanBox
        visible: home.mode === "scan"
        x: 120 * root.s; y: 260 * root.s
        width: 1400 * root.s; height: 600 * root.s
        property int sel: 0
        Text {
            text: home.scanning
                  ? "Recherche sur " + home.octets[0] + "." + home.octets[1] + "." + home.octets[2] + ".x … " + home.scanDone + "/254"
                  : "Recherche terminée : " + home.found.length + " PC trouvé(s)"
            color: "white"; font.pixelSize: 36 * root.s
        }
        Column {
            y: 80 * root.s
            spacing: 12 * root.s
            Repeater {
                model: home.found
                Rectangle {
                    width: 1100 * root.s; height: 84 * root.s; radius: 14 * root.s
                    color: index === scanBox.sel ? "#2b6cff" : "#1a2230"
                    Text {
                        anchors.verticalCenter: parent.verticalCenter
                        x: 30 * root.s
                        text: modelData.name + "  (" + modelData.host + ")"
                        color: "white"; font.pixelSize: 34 * root.s
                    }
                }
            }
        }
        Keys.onPressed: {
            var k = event.key;
            event.accepted = true;
            if (k === Qt.Key_Up) scanBox.sel = Math.max(0, scanBox.sel - 1);
            else if (k === Qt.Key_Down) scanBox.sel = Math.min(home.found.length - 1, scanBox.sel + 1);
            else if ((k === Qt.Key_Return || k === Qt.Key_Enter || k === Qt.Key_Select) && home.found.length) {
                home.scanning = false;
                mode = "list"; menuList.forceActiveFocus();
                connectTo(home.found[scanBox.sel].host, 8765);
            } else if (k === Qt.Key_Escape || k === Qt.Key_Back) {
                home.scanning = false;
                mode = "list"; menuList.forceActiveFocus();
            } else event.accepted = false;
        }
    }

    Text {
        id: statusText
        x: 120 * root.s
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 140 * root.s
        color: "#ffcf5d"
        font.pixelSize: 32 * root.s
    }
    Text {
        x: 120 * root.s
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 80 * root.s
        text: "Touche rouge : oublier un PC • Réglages stockés " + (store.persistent ? "sur le Player" : "en mémoire seulement")
        color: "#56677f"
        font.pixelSize: 24 * root.s
    }
}
