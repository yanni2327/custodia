// Menú emergente propio (perfil, clic derecho). Cubre toda la vista con una
// capa invisible que lo cierra al pulsar fuera, y aparece con un fundido y
// una ligera escala.
//
// Cada opción es un objeto JS:
//   { texto, glifo, accion, peligro, atajo, desactivada }
//   { separador: true }
//   { cabecera: true, texto }
import QtQuick
import QtQuick.Effects

Item {
    id: menu
    anchors.fill: parent
    z: 1000

    property var opciones: []
    property bool abierto: false
    property real px: 0
    property real py: 0
    property real anchoMenu: 260

    signal elegido(string accion)

    visible: abierto || caja.opacity > 0.01

    function abrir(x, y, ops) {
        opciones = ops
        px = x
        py = y
        abierto = true
    }
    function cerrar() { abierto = false }

    MouseArea {
        anchors.fill: parent
        enabled: menu.abierto
        acceptedButtons: Qt.AllButtons
        onPressed: menu.cerrar()
        onWheel: menu.cerrar()
    }

    Rectangle {
        id: caja
        width: menu.anchoMenu
        height: columna.implicitHeight + 14
        x: Math.min(Math.max(8, menu.px), menu.width - width - 8)
        y: (menu.py + height > menu.height - 8) ? Math.max(8, menu.py - height) : menu.py
        radius: 12
        color: T.PANEL
        border.color: T.BORDE
        border.width: 1

        opacity: menu.abierto ? 1 : 0
        scale: menu.abierto ? 1 : 0.95
        transformOrigin: Item.Top
        Behavior on opacity { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
        Behavior on scale { NumberAnimation { duration: 170; easing.type: Easing.OutCubic } }

        layer.enabled: true
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: "#000000"
            shadowOpacity: oscuro ? 0.6 : 0.16
            shadowBlur: 0.8
            blurMax: 32
            shadowVerticalOffset: 8
        }

        // Evita que un clic dentro de la caja llegue a la capa que cierra.
        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons }

        Column {
            id: columna
            x: 7
            y: 7
            width: parent.width - 14

            Repeater {
                model: menu.opciones

                Item {
                    id: opcion
                    required property var modelData
                    readonly property bool esSeparador: !!modelData.separador
                    readonly property bool esCabecera: !!modelData.cabecera
                    readonly property bool desactivada: !!modelData.desactivada
                    width: columna.width
                    height: esSeparador ? 13 : 38

                    Rectangle {
                        visible: opcion.esSeparador
                        anchors.verticalCenter: parent.verticalCenter
                        x: 6
                        width: parent.width - 12
                        height: 1
                        color: T.BORDE
                    }

                    Rectangle {
                        visible: !opcion.esSeparador
                        anchors.fill: parent
                        radius: 8
                        color: zona.containsMouse && !opcion.esCabecera && !opcion.desactivada
                               ? (opcion.modelData.peligro ? Qt.alpha(T.NEGADO, 0.13)
                                                           : Qt.alpha(T.ACENTO, 0.13))
                               : "transparent"
                        Behavior on color { ColorAnimation { duration: 110 } }

                        readonly property color tinta: opcion.esCabecera ? T.TINTA_TENUE
                            : opcion.desactivada ? T.TINTA_TENUE
                            : zona.containsMouse ? (opcion.modelData.peligro ? T.NEGADO : T.ACENTO)
                            : (opcion.modelData.peligro ? T.NEGADO : T.TINTA)

                        Text {
                            id: glifo
                            x: 12
                            anchors.verticalCenter: parent.verticalCenter
                            text: opcion.modelData.glifo || ""
                            font.family: iconos
                            font.pixelSize: 14
                            color: parent.tinta
                        }
                        Text {
                            x: opcion.modelData.glifo ? 40 : 12
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width - x - (atajo.visible ? atajo.width + 18 : 12)
                            elide: Text.ElideRight
                            text: opcion.modelData.texto || ""
                            font.family: fuente
                            font.pixelSize: opcion.esCabecera ? 12 : 13
                            font.weight: opcion.esCabecera ? Font.DemiBold : Font.Normal
                            color: parent.tinta
                        }
                        Text {
                            id: atajo
                            visible: !!opcion.modelData.atajo
                            anchors.right: parent.right
                            anchors.rightMargin: 12
                            anchors.verticalCenter: parent.verticalCenter
                            text: opcion.modelData.atajo || ""
                            font.family: fuente
                            font.pixelSize: 11
                            color: T.TINTA_TENUE
                        }

                        MouseArea {
                            id: zona
                            anchors.fill: parent
                            hoverEnabled: true
                            enabled: !opcion.esCabecera && !opcion.desactivada
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                menu.cerrar()
                                menu.elegido(opcion.modelData.accion)
                            }
                        }
                    }
                }
            }
        }
    }
}
