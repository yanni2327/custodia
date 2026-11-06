// Botón con estados de hover, pulsado y "ocupado" (tres puntos animados).
// Variantes: primario (relleno de acento), secundario (contorno) y peligro
// (relleno rojo, para acciones que no se pueden deshacer). Icono opcional.
import QtQuick

Rectangle {
    id: boton

    property string texto: ""
    property string glifo: ""
    property bool primario: true
    property bool peligro: false
    property bool ocupado: false

    signal pulsado()

    readonly property color base: peligro ? T.NEGADO : T.ACENTO
    readonly property bool relleno: primario || peligro
    readonly property color tinta: relleno ? "white" : (peligro ? T.NEGADO : T.TINTA)

    implicitHeight: 44
    implicitWidth: contenido.implicitWidth + 36
    radius: 11
    color: relleno
           ? (zona.pressed ? Qt.darker(base, 1.15)
              : zona.containsMouse ? Qt.lighter(base, 1.1) : base)
           : (zona.containsMouse ? T.ELEVADO : "transparent")
    border.width: relleno ? 0 : 1
    border.color: T.BORDE
    Behavior on color { ColorAnimation { duration: 140 } }

    scale: zona.pressed ? 0.97 : 1.0
    Behavior on scale { NumberAnimation { duration: 120; easing.type: Easing.OutCubic } }

    Row {
        id: contenido
        anchors.centerIn: parent
        spacing: 8
        opacity: boton.ocupado ? 0 : 1
        Behavior on opacity { NumberAnimation { duration: 120 } }
        Text {
            visible: boton.glifo.length > 0
            anchors.verticalCenter: parent.verticalCenter
            text: boton.glifo
            font.family: iconos
            font.pixelSize: 14
            color: boton.tinta
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: boton.texto
            color: boton.tinta
            font.family: fuente
            font.pixelSize: 14
            font.weight: Font.DemiBold
        }
    }

    Row {
        anchors.centerIn: parent
        spacing: 7
        opacity: boton.ocupado ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 120 } }

        Repeater {
            model: 3
            Rectangle {
                width: 7; height: 7; radius: 3.5
                color: boton.tinta
                opacity: 0.3
                SequentialAnimation on opacity {
                    running: boton.ocupado
                    loops: Animation.Infinite
                    PauseAnimation { duration: index * 150 }
                    NumberAnimation { from: 0.3; to: 1; duration: 300; easing.type: Easing.InOutSine }
                    NumberAnimation { from: 1; to: 0.3; duration: 300; easing.type: Easing.InOutSine }
                    PauseAnimation { duration: (2 - index) * 150 }
                }
            }
        }
    }

    MouseArea {
        id: zona
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        enabled: !boton.ocupado
        onClicked: boton.pulsado()
    }
}
