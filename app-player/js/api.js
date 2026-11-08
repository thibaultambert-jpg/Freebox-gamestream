.pragma library
// ============================================================
//  Client HTTP minimal vers l'agent PC (XMLHttpRequest QML).
//  JavaScript ES5 uniquement (var, function) : le moteur JS du
//  Player peut être ancien, on évite let/const/=>/`template`.
// ============================================================

var base = "";       // ex : "http://192.168.1.10:8765"
var host = "";
var port = 8765;
var token = "";
var later = null;    // fonction (ms, callback) fournie par main.qml (pas de setTimeout en QML)

function init(laterFn) {
    later = laterFn;
}

function setServer(h, p, tok) {
    host = h;
    port = p || 8765;
    base = "http://" + host + ":" + port;
    token = tok || "";
}

// Requête générique. cb(status, json) ; status = 0 en cas d'échec réseau ou de délai dépassé.
function request(method, url, body, cb, timeoutMs) {
    var xhr = new XMLHttpRequest();
    var done = false;
    xhr.onreadystatechange = function () {
        if (xhr.readyState !== 4 || done)
            return;
        done = true;
        var data = null;
        try { data = JSON.parse(xhr.responseText); } catch (e) { data = null; }
        if (cb) cb(xhr.status, data);
    };
    xhr.open(method, url);
    if (token)
        xhr.setRequestHeader("X-FreeStream-Token", token);
    if (body !== null && body !== undefined)
        xhr.setRequestHeader("Content-Type", "application/json");
    xhr.send(body !== null && body !== undefined ? JSON.stringify(body) : null);
    // Le XMLHttpRequest QML n'a pas toujours de propriété timeout : on la simule.
    if (timeoutMs && later) {
        later(timeoutMs, function () {
            if (done) return;
            done = true;
            try { xhr.abort(); } catch (e) {}
            if (cb) cb(0, null);
        });
    }
    return xhr;
}

function get(path, cb, timeoutMs) {
    return request("GET", base + path, null, cb, timeoutMs || 5000);
}

function post(path, body, cb, timeoutMs) {
    return request("POST", base + path, body || {}, cb, timeoutMs || 5000);
}

// Requête vers une URL absolue (scan du réseau)
function getUrl(url, cb, timeoutMs) {
    return request("GET", url, null, cb, timeoutMs || 1500);
}

// Horloge en millisecondes
function now() {
    return new Date().getTime();
}

// Médiane d'un tableau de nombres
function median(arr) {
    if (!arr.length) return -1;
    var a = arr.slice().sort(function (x, y) { return x - y; });
    return a[Math.floor(a.length / 2)];
}
