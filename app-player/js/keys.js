.pragma library
// ============================================================
//  Normalisation des touches : code Qt -> nom stable.
//  Les noms sont ceux utilisés dans les profils de l'agent
//  (agent-pc/freestream/config.py). Une touche inconnue donne
//  "code:<entier>" : utilisez la sonde (Phase 0) pour découvrir
//  les codes de la télécommande et de la manette, puis ajoutez-les
//  dans un profil de l'agent, sans redéployer l'app.
// ============================================================

var table = null;

// Associe chaque constante Qt.Key_* existante à un nom.
// On teste l'existence de chaque constante (selon la version de Qt).
function build() {
    var pairs = [
        ["Key_Up", "Up"], ["Key_Down", "Down"], ["Key_Left", "Left"], ["Key_Right", "Right"],
        ["Key_Return", "Select"], ["Key_Enter", "Select"], ["Key_Select", "Select"],
        ["Key_Space", "Space"],
        ["Key_Escape", "Back"], ["Key_Back", "Back"], ["Key_Backspace", "Back"],
        ["Key_Menu", "Menu"], ["Key_Context1", "Menu"], ["Key_Info", "Info"], ["Key_Guide", "Info"],
        ["Key_Red", "Red"], ["Key_Green", "Green"], ["Key_Yellow", "Yellow"], ["Key_Blue", "Blue"],
        ["Key_ChannelUp", "ChannelUp"], ["Key_PageUp", "ChannelUp"],
        ["Key_ChannelDown", "ChannelDown"], ["Key_PageDown", "ChannelDown"],
        ["Key_MediaPlay", "Play"], ["Key_MediaTogglePlayPause", "Play"], ["Key_Play", "Play"],
        ["Key_MediaPause", "Play"], ["Key_MediaStop", "Stop"],
        ["Key_MediaNext", "Next"], ["Key_MediaPrevious", "Previous"],
        ["Key_AudioForward", "Forward"], ["Key_AudioRewind", "Rewind"],
        ["Key_MediaRecord", "Record"], ["Key_Home", "Home"], ["Key_HomePage", "Home"],
        ["Key_VolumeUp", "VolumeUp"], ["Key_VolumeDown", "VolumeDown"], ["Key_VolumeMute", "Mute"]
    ];
    table = {};
    for (var i = 0; i < pairs.length; i++) {
        var code = Qt[pairs[i][0]];
        if (code !== undefined && table[code] === undefined)
            table[code] = pairs[i][1];
    }
    // Chiffres 0-9 et lettres A-Z (clavier USB/Bluetooth branché au Player)
    for (var d = 0; d <= 9; d++)
        table[0x30 + d] = String(d);
    for (var l = 0; l < 26; l++)
        table[0x41 + l] = String.fromCharCode(0x41 + l);
}

// Nom normalisé d'un code Qt
function nameOf(code) {
    if (table === null)
        build();
    var n = table[code];
    return n !== undefined ? n : "code:" + code;
}

// Événement prêt à envoyer à l'agent
function toEvent(event, down) {
    return { k: nameOf(event.key), c: event.key, d: down ? 1 : 0, r: event.isAutoRepeat ? 1 : 0 };
}
