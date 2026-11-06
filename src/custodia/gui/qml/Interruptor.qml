// Interruptor de encendido/apagado con su texto al lado.
import QtQuick

Item {
    id: interruptor

    property bool marcado: false
    property string texto: ""
    property string detalle: ""

    implicitWidth: pista.width + 12 + textos.implicitWidth
    implicitHeight: Math.max(pista.height, textos.implicitHeight)

    Rectangle {
        id: pista
        width: 40; height: 24; radius: 12
        anchors.top: parent.top
        anchors.topMargin: textos.implicitHeight > 30 ? 2 : (parent.height - height) / 2
        color: interruptor.marcado ? T.ACENTO : (oscuro ? "#3A3A42" : "#D5DAE0")
        Behavior on color { ColorAnimation { duration: 160 } }
        Rectangle {
            width: 18; height: 18; radius: 9
            y: 3
            x: interruptor.marcado ? parent.width - width - 3 : 3
            color: "white"
            Behavior on x { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
        }
    }
    Column {
        id: textos
        anchors.left: pista.right
        anchors.leftMargin: 12
        anchors.right: parent.right
        anchors.verticalCenter: textos.implicitHeight > 30 ? undefined : parent.verticalCenter
        spacing: 2
        Text {
            width: parent.width
            wrapMode: Text.WordWrap
            text: interruptor.texto
            color: T.TINTA
            font.family: fuente
            font.pixelSize: 13
            font.weight: Font.Medium
        }
        Text {
            visible: interruptor.detalle.length > 0
            width: parent.width
            wrapMode: Text.WordWrap
            text: interruptor.detalle
            color: T.TINTA_MEDIA
            font.family: fuente
            font.pixelSize: 12
        }
    }
    MouseArea {
        anchors.fill: parent
        cursorShape: Qt.PointingHandCursor
        onClicked: interruptor.marcado = !interruptor.marcado
    }
}
