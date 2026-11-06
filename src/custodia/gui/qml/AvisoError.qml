// Franja de error que aparece desplegándose cuando hay mensaje.
import QtQuick

Item {
    id: aviso
    property string mensaje: ""
    // Se recuerda el último texto para que no desaparezca de golpe al ocultarse.
    property string _texto: ""
    onMensajeChanged: if (mensaje.length > 0) _texto = mensaje

    readonly property bool abierto: mensaje.length > 0
    height: abierto ? caja.height : 0
    opacity: abierto ? 1 : 0
    visible: height > 0.5
    clip: true
    Behavior on height { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
    Behavior on opacity { NumberAnimation { duration: 180 } }

    Rectangle {
        id: caja
        width: parent.width
        height: texto.implicitHeight + 22
        radius: 9
        color: Qt.alpha(T.NEGADO, 0.13)
        border.color: Qt.alpha(T.NEGADO, 0.35)
        border.width: 1

        Text {
            id: icono
            text: ""
            font.family: iconos
            font.pixelSize: 14
            color: T.NEGADO
            anchors.left: parent.left
            anchors.leftMargin: 12
            anchors.top: parent.top
            anchors.topMargin: 12
        }
        Text {
            id: texto
            text: aviso._texto
            anchors.left: icono.right
            anchors.leftMargin: 10
            anchors.right: parent.right
            anchors.rightMargin: 12
            anchors.verticalCenter: parent.verticalCenter
            wrapMode: Text.WordWrap
            color: T.NEGADO
            font.family: fuente
            font.pixelSize: 13
            font.weight: Font.Medium
        }
    }
}
