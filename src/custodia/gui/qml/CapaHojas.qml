// Capa que presenta las hojas de administración (cuentas, bitácora, permisos,
// verificación en dos pasos, clave de confirmación) como un panel grande
// sobre la ventana, que queda desenfocada detrás.
//
// Cada hoja es un archivo Hoja<Nombre>.qml que expone:
//   titulo, subtitulo       textos de la cabecera
//   anchoPreferido          0 = todo el ancho disponible
//   altoPreferido           0 = todo el alto disponible
//   c                       su controlador de Python (hojas.py)
import QtQuick
import QtQuick.Effects

Item {
    id: capa
    anchors.fill: parent
    z: 50

    property Item fondo
    property var c: null
    property string mostrada: ""
    property real progreso: 0

    visible: mostrada !== ""

    Connections {
        target: puente
        function onHojaChanged() {
            if (puente.hoja !== "") {
                salida.stop()
                capa.c = puente.ctrl
                capa.mostrada = puente.hoja
                entrada.restart()
            } else if (capa.mostrada !== "") {
                salida.restart()
            }
        }
    }

    NumberAnimation {
        id: entrada
        target: capa; property: "progreso"; to: 1
        duration: 340; easing.type: Easing.OutCubic
    }
    SequentialAnimation {
        id: salida
        NumberAnimation { target: capa; property: "progreso"; to: 0; duration: 200; easing.type: Easing.InCubic }
        // Primero se descarga la hoja y luego se suelta el controlador, para
        // que ningún enlace de la hoja llegue a leer un controlador nulo.
        ScriptAction { script: { capa.mostrada = ""; capa.c = null } }
    }

    // ---- fondo: la ventana desenfocada --------------------------------------
    MultiEffect {
        anchors.fill: parent
        source: capa.visible ? capa.fondo : null
        blurEnabled: true
        blur: 0.9
        blurMax: 32
        autoPaddingEnabled: false
        opacity: capa.progreso
        visible: capa.visible && capa.fondo !== null
    }
    Rectangle {
        anchors.fill: parent
        color: Qt.alpha("#05070C", oscuro ? 0.5 : 0.26)
        opacity: capa.progreso
    }
    // Un clic fuera de la hoja la cierra; nada de lo de detrás responde.
    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.AllButtons
        onWheel: (ev) => ev.accepted = true
        onClicked: puente.cerrarHoja()
    }

    // ---- la hoja ------------------------------------------------------------
    Rectangle {
        id: tarjeta
        readonly property var it: cargador.item
        readonly property real anchoMax: capa.width - 56
        readonly property real altoMax: capa.height - 44
        width: it && it.anchoPreferido > 0 ? Math.min(it.anchoPreferido, anchoMax) : anchoMax
        height: it && it.altoPreferido > 0
                ? Math.min(it.altoPreferido + cabecera.height + 26 + 28 + 26, altoMax)
                : altoMax
        Behavior on height { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
        anchors.centerIn: parent
        anchors.verticalCenterOffset: (1 - capa.progreso) * 28
        opacity: capa.progreso
        scale: 0.97 + 0.03 * capa.progreso
        radius: 22
        color: T.PANEL
        border.color: T.BORDE

        layer.enabled: true
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: "#000000"
            shadowOpacity: oscuro ? 0.6 : 0.2
            shadowBlur: 1.0
            blurMax: 56
            shadowVerticalOffset: 18
        }

        // Los clics dentro de la hoja no la cierran.
        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons }

        Item {
            id: cabecera
            x: 32
            y: 26
            width: parent.width - 64
            height: Math.max(textos.implicitHeight, 40)

            Column {
                id: textos
                anchors.left: parent.left
                anchors.right: cerrar.left
                anchors.rightMargin: 16
                spacing: 4
                Text {
                    width: parent.width
                    elide: Text.ElideRight
                    text: tarjeta.it ? tarjeta.it.titulo : ""
                    color: T.TINTA
                    font.family: fuente
                    font.pixelSize: 24
                    font.weight: Font.Bold
                    font.letterSpacing: -0.3
                }
                Text {
                    visible: text.length > 0
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: tarjeta.it ? tarjeta.it.subtitulo : ""
                    color: T.TINTA_MEDIA
                    font.family: fuente
                    font.pixelSize: 14
                }
            }
            IconoBoton {
                id: cerrar
                anchors.right: parent.right
                anchors.top: parent.top
                glifo: ""
                tamGlifo: 13
                pista: "Cerrar (Esc)"
                onPulsado: puente.cerrarHoja()
            }
        }

        // Las hojas de alto propio (verificación, clave) se desplazan si la
        // pantalla es baja; las de alto completo ocupan justo el hueco.
        Flickable {
            id: despl
            anchors.top: cabecera.bottom
            anchors.topMargin: 26
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            anchors.leftMargin: 32
            anchors.rightMargin: 32
            anchors.bottomMargin: 28
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            contentWidth: width
            contentHeight: tarjeta.it && tarjeta.it.altoPreferido > 0
                           ? Math.max(height, tarjeta.it.altoPreferido) : height
            interactive: contentHeight > height + 1

            Loader {
                id: cargador
                width: despl.width
                height: despl.contentHeight
                source: capa.mostrada
                        ? "Hoja" + capa.mostrada.charAt(0).toUpperCase() + capa.mostrada.slice(1) + ".qml"
                        : ""
                onLoaded: item.c = Qt.binding(() => capa.c)
            }
        }
        Rectangle {
            visible: despl.interactive
            anchors.right: parent.right
            anchors.rightMargin: 8
            width: 4
            radius: 2
            color: T.TINTA_TENUE
            opacity: despl.moving ? 0.8 : 0.35
            Behavior on opacity { NumberAnimation { duration: 200 } }
            y: despl.y + despl.height * despl.visibleArea.yPosition
            height: despl.height * despl.visibleArea.heightRatio
        }
    }
}
