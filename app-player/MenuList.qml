// ============================================================
//  Liste verticale navigable à la télécommande.
//  model : tableau JS [{label: "...", value: "..."}]
//  Haut/Bas : sélection ; OK : activated ; Gauche/Droite : changed(-1/+1)
// ============================================================
import QtQuick 2.0

FocusScope {
    id: list
    property var model: []
    property int currentIndex: 0
    property real s: 1
    property real rowHeight: 84 * s

    signal activated(int index)
    signal changed(int index, int delta)
    signal otherKey(var event)   // touches non gérées par la liste

    width: 900 * s
    height: Math.max(1, model.length) * (rowHeight + 12 * s)

    Column {
        spacing: 12 * list.s
        Repeater {
            model: list.model
            Rectangle {
                width: list.width
                height: list.rowHeight
                radius: 14 * list.s
                color: index === list.currentIndex && list.activeFocus ? "#2b6cff" : "#1a2230"
                border.color: index === list.currentIndex ? "#5d8cff" : "transparent"
                border.width: 3 * list.s
                Text {
                    anchors.left: parent.left
                    anchors.leftMargin: 30 * list.s
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.label
                    color: "white"
                    font.pixelSize: 34 * list.s
                }
                Text {
                    anchors.right: parent.right
                    anchors.rightMargin: 30 * list.s
                    anchors.verticalCenter: parent.verticalCenter
                    text: modelData.value !== undefined ? "◀  " + modelData.value + "  ▶" : ""
                    color: "#cfe0ff"
                    font.pixelSize: 32 * list.s
                }
            }
        }
    }

    Keys.onUpPressed: currentIndex = (currentIndex - 1 + model.length) % model.length
    Keys.onDownPressed: currentIndex = (currentIndex + 1) % model.length
    Keys.onLeftPressed: changed(currentIndex, -1)
    Keys.onRightPressed: changed(currentIndex, 1)
    Keys.onReturnPressed: activated(currentIndex)
    Keys.onEnterPressed: activated(currentIndex)
    Keys.onPressed: {
        if (event.key === Qt.Key_Select) {
            activated(currentIndex);
            event.accepted = true;
        } else if (event.key !== Qt.Key_Up && event.key !== Qt.Key_Down && event.key !== Qt.Key_Left
                   && event.key !== Qt.Key_Right && event.key !== Qt.Key_Return && event.key !== Qt.Key_Enter) {
            otherKey(event);
        }
    }
}
