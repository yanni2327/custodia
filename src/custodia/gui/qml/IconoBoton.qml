// Botón cuadrado con un icono de la fuente de Windows y una pista (tooltip)
// que aparece con un pequeño retraso al dejar el ratón encima.
import QtQuick

Rectangle {
    id: boton

    property string glifo: ""
    property string pista: ""
    property bool peligro: false
    property bool activo: true
    property bool pistaArriba: false
    property int lado: 38
    property int tamGlifo: 16

    signal pulsado()

    width: lado
    height: lado
    radius: 10
    color: zona.containsMouse && activo
           ? (peligro ? Qt.alpha(T.NEGADO, 0.14) : T.ELEVADO) : "transparent"
    Behavior on color { ColorAnimation { duration: 140 } }

    property bool _mostrarPista: false

    Text {
        anchors.centerIn: parent
        text: boton.glifo
        font.family: iconos
        font.pixelSize: boton.tamGlifo
        color: !boton.activo ? T.TINTA_TENUE
             : zona.containsMouse ? (boton.peligro ? T.NEGADO : T.ACENTO)
             : T.TINTA_MEDIA
        opacity: boton.activo ? 1 : 0.45
        scale: zona.pressed && boton.activo ? 0.86 : 1
        Behavior on color { ColorAnimation { duration: 140 } }
        Behavior on opacity { NumberAnimation { duration: 140 } }
        Behavior on scale { NumberAnimation { duration: 110; easing.type: Easing.OutCubic } }
    }

    MouseArea {
        id: zona
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: boton.activo ? Qt.PointingHandCursor : Qt.ArrowCursor
        onClicked: if (boton.activo) boton.pulsado()
        onContainsMouseChanged: if (!containsMouse) boton._mostrarPista = false
        onPressed: boton._mostrarPista = false
    }

    Timer {
        interval: 450
        running: zona.containsMouse && boton.pista.length > 0 && !boton._mostrarPista
        onTriggered: boton._mostrarPista = true
    }

    // Pista.
    Rectangle {
        z: 100
        anchors.horizontalCenter: parent.horizontalCenter
        y: boton.pistaArriba ? -height - 8 : parent.height + 8
        width: textoPista.implicitWidth + 20
        height: textoPista.implicitHeight + 12
        radius: 7
        color: oscuro ? "#2A2A30" : "#1F2933"
        opacity: boton._mostrarPista ? 1 : 0
        visible: opacity > 0
        Behavior on opacity { NumberAnimation { duration: 140 } }

        Text {
            id: textoPista
            anchors.centerIn: parent
            text: boton.pista
            color: "white"
            font.family: fuente
            font.pixelSize: 12
        }
    }
}
