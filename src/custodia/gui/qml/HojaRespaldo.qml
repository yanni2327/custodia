// Respaldo de la clave maestra (C13): elegir la acción y, después, exportar o
// restaurar. Las contraseñas solo pasan al controlador al confirmar.
import QtQuick

Item {
    id: hoja

    property var c
    property string vista: "inicio"
    property string error: ""
    readonly property bool ocupado: c ? c.ocupado : false

    readonly property string titulo: vista === "exportar" ? "Exportar respaldo"
                                   : vista === "restaurar" ? "Restaurar respaldo"
                                   : "Respaldo de la clave"
    readonly property string subtitulo: ""
    readonly property int anchoPreferido: 560
    readonly property int altoPreferido: columna.implicitHeight

    function ir(destino) {
        error = ""
        rec1.text = ""
        rec2.text = ""
        recRestaurar.text = ""
        vista = destino
        if (destino === "exportar") rec1.enfocar()
        else if (destino === "restaurar") recRestaurar.enfocar()
    }

    Connections {
        target: hoja.c
        function onError(mensaje) {
            hoja.error = mensaje
            if (hoja.vista === "restaurar") {
                recRestaurar.text = ""
                recRestaurar.enfocar()
            } else {
                rec2.text = ""
                rec1.enfocar()
            }
        }
    }

    Column {
        id: columna
        width: parent.width
        spacing: 0

        // ---- advertencia ---------------------------------------------------
        Rectangle {
            width: parent.width
            height: textoAviso.implicitHeight + 24
            radius: 10
            color: Qt.alpha("#F59E0B", 0.13)
            border.color: Qt.alpha("#F59E0B", 0.4)
            Text {
                id: icoAviso
                x: 12; y: 12
                text: ""
                font.family: iconos
                font.pixelSize: 14
                color: "#D97706"
            }
            Text {
                id: textoAviso
                anchors.left: icoAviso.right
                anchors.leftMargin: 10
                anchors.right: parent.right
                anchors.rightMargin: 12
                y: 12
                wrapMode: Text.WordWrap
                lineHeight: 1.25
                text: "Quien tenga el archivo de respaldo y su contraseña puede descifrar todos los archivos de Custodia. Guárdalos en lugares distintos. Si pierdes la contraseña, el respaldo no se puede abrir."
                color: T.TINTA
                font.family: fuente
                font.pixelSize: 13
            }
        }
        Item { width: 1; height: 18 }

        // ---- elegir acción -------------------------------------------------
        Column {
            width: parent.width
            spacing: 10
            visible: hoja.vista === "inicio"

            Repeater {
                model: [
                    { t: "Exportar respaldo", d: "Guarda la clave cifrada con una contraseña de recuperación", g: "", v: "exportar" },
                    { t: "Restaurar respaldo", d: "Recupera la clave desde un archivo, también en un equipo nuevo", g: "", v: "restaurar" }
                ]
                Rectangle {
                    id: opcion
                    required property var modelData
                    width: columna.width
                    height: 68
                    radius: 14
                    color: zonaOpcion.containsMouse ? Qt.alpha(T.ACENTO, oscuro ? 0.14 : 0.08) : (oscuro ? T.FONDO : T.ELEVADO)
                    border.color: zonaOpcion.containsMouse ? Qt.alpha(T.ACENTO, 0.45) : "transparent"
                    Behavior on color { ColorAnimation { duration: 140 } }
                    Text {
                        id: icoOpcion
                        x: 18
                        anchors.verticalCenter: parent.verticalCenter
                        text: opcion.modelData.g
                        font.family: iconos
                        font.pixelSize: 20
                        color: T.ACENTO
                    }
                    Column {
                        anchors.left: icoOpcion.right
                        anchors.leftMargin: 16
                        anchors.right: parent.right
                        anchors.rightMargin: 16
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 2
                        Text { text: opcion.modelData.t; color: T.TINTA; font.family: fuente; font.pixelSize: 14; font.weight: Font.DemiBold }
                        Text { width: parent.width; elide: Text.ElideRight; text: opcion.modelData.d; color: T.TINTA_MEDIA; font.family: fuente; font.pixelSize: 12 }
                    }
                    MouseArea {
                        id: zonaOpcion
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: hoja.ir(opcion.modelData.v)
                    }
                }
            }
        }

        // ---- exportar ------------------------------------------------------
        Column {
            width: parent.width
            spacing: 14
            visible: hoja.vista === "exportar"

            Campo {
                id: rec1
                width: parent.width
                rotulo: "Contraseña de recuperación"
                marcador: "Al menos 12 caracteres"
                icono: ""
                esPassword: true
                conError: hoja.error.length > 0
                onAceptado: rec2.enfocar()
                onTeclaSoltada: hoja.error = ""
            }
            Campo {
                id: rec2
                width: parent.width
                rotulo: "Repite la contraseña"
                icono: ""
                esPassword: true
                conError: hoja.error.length > 0
                onAceptado: hoja.c.exportar(rec1.text, rec2.text)
                onTeclaSoltada: hoja.error = ""
            }
        }

        // ---- restaurar -----------------------------------------------------
        Column {
            width: parent.width
            spacing: 14
            visible: hoja.vista === "restaurar"

            Text {
                width: parent.width
                wrapMode: Text.WordWrap
                lineHeight: 1.25
                text: "En un equipo nuevo, copia antes el almacén para poder comprobar la clave con tus archivos."
                color: T.TINTA_MEDIA
                font.family: fuente
                font.pixelSize: 13
            }
            Item {
                width: parent.width
                height: 44
                Text {
                    anchors.left: parent.left
                    anchors.right: elegir.left
                    anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    elide: Text.ElideMiddle
                    text: hoja.c && hoja.c.archivo ? hoja.c.archivo : "Ningún archivo elegido"
                    color: hoja.c && hoja.c.archivo ? T.TINTA : T.TINTA_TENUE
                    font.family: fuente
                    font.pixelSize: 13
                }
                Boton {
                    id: elegir
                    anchors.right: parent.right
                    primario: false
                    texto: "Elegir archivo"
                    onPulsado: { hoja.error = ""; hoja.c.elegirArchivo() }
                }
            }
            Campo {
                id: recRestaurar
                width: parent.width
                rotulo: "Contraseña de recuperación"
                icono: ""
                esPassword: true
                conError: hoja.error.length > 0
                onAceptado: hoja.c.restaurar(recRestaurar.text)
                onTeclaSoltada: hoja.error = ""
            }
        }

        Item { width: 1; height: 12; visible: hoja.error.length > 0 }
        AvisoError { width: parent.width; mensaje: hoja.error }

        // ---- botones -------------------------------------------------------
        Item { width: 1; height: 22; visible: hoja.vista !== "inicio" }
        Item {
            width: parent.width
            height: 44
            visible: hoja.vista !== "inicio"
            Row {
                anchors.right: parent.right
                spacing: 10
                Boton { primario: false; texto: "Volver"; onPulsado: hoja.ir("inicio") }
                Boton {
                    visible: hoja.vista === "exportar"
                    texto: "Exportar"
                    ocupado: hoja.ocupado
                    onPulsado: hoja.c.exportar(rec1.text, rec2.text)
                }
                Boton {
                    visible: hoja.vista === "restaurar"
                    peligro: true
                    texto: "Restaurar"
                    ocupado: hoja.ocupado
                    onPulsado: hoja.c.restaurar(recRestaurar.text)
                }
            }
        }
    }
}
