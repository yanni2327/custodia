// Verificación en dos pasos de la propia cuenta: tres estados.
//  inactivo    explicación y botón para activarla
//  configurar  los pasos para dar de alta la clave en la app y confirmarla
//  activo      estado y opción de desactivarla
import QtQuick

Item {
    id: hoja

    property var c
    readonly property string titulo: "Verificación en dos pasos"
    readonly property string subtitulo: ""
    readonly property int anchoPreferido: 560
    readonly property int altoPreferido: columna.implicitHeight
    readonly property string estado: c ? c.estado : ""
    property string error: ""
    property bool verClave: false

    onEstadoChanged: {
        error = ""
        if (estado === "configurar") enfocar.restart()
    }
    Timer { id: enfocar; interval: 80; onTriggered: codigo.enfocar() }

    Connections {
        target: hoja.c
        ignoreUnknownSignals: true
        function onError(m) {
            hoja.error = m
            codigo.conError = true
            codigo.limpiar()
            codigo.enfocar()
        }
    }

    Column {
        id: columna
        width: parent.width
        spacing: 0

        // ---- cabecera de estado: icono y frase -------------------------------
        Row {
            width: parent.width
            spacing: 16
            Rectangle {
                width: 56; height: 56; radius: 18
                color: Qt.alpha(hoja.estado === "activo" ? T.VERDE : T.ACENTO, 0.14)
                Text {
                    anchors.centerIn: parent
                    text: hoja.estado === "activo" ? "" : ""
                    font.family: iconos
                    font.pixelSize: 22
                    color: hoja.estado === "activo" ? T.VERDE : T.ACENTO
                }
            }
            Column {
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width - 72
                spacing: 4
                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: hoja.estado === "activo" ? "Activada en tu cuenta"
                        : hoja.estado === "configurar" ? "Configura tu app de autenticación"
                        : "Desactivada"
                    color: T.TINTA
                    font.family: fuente
                    font.pixelSize: 17
                    font.weight: Font.Bold
                }
                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    lineHeight: 1.25
                    text: hoja.estado === "activo"
                        ? "Se te pide un código de 6 dígitos al entrar y antes de eliminar, descargar, añadir, renombrar, cambiar permisos o administrar cuentas."
                        : hoja.estado === "configurar"
                        ? "Son dos pasos. Si cierras esto antes de confirmar, no se activa."
                        : "Hace falta para eliminar, descargar, añadir o renombrar archivos, cambiar permisos y administrar cuentas. Usa un código de 6 dígitos de una app como Google Authenticator, Authy o Microsoft Authenticator, también al entrar."
                    color: T.TINTA_MEDIA
                    font.family: fuente
                    font.pixelSize: 13
                }
            }
        }

        // ---- pasos (solo al configurar) -------------------------------------
        // Es una secuencia de verdad, por eso va numerada; la clave y el
        // código van justo debajo del paso que los pide.
        component Paso: Item {
            id: paso
            property int numero: 1
            property string texto: ""
            width: parent ? parent.width : 0
            height: Math.max(circulo.height, textoPaso.implicitHeight)
            visible: hoja.estado === "configurar"
            Rectangle {
                id: circulo
                width: 26; height: 26; radius: 13
                color: T.ACENTO
                Text { anchors.centerIn: parent; text: paso.numero; color: "white"; font.family: fuente; font.pixelSize: 12; font.weight: Font.Bold }
            }
            Text {
                id: textoPaso
                anchors.left: circulo.right
                anchors.leftMargin: 12
                anchors.right: parent.right
                y: 3
                wrapMode: Text.WordWrap
                text: paso.texto
                color: T.TINTA
                font.family: fuente
                font.pixelSize: 13
            }
        }

        Item { width: 1; height: 22; visible: hoja.estado === "configurar" }
        Paso { numero: 1; texto: "Abre tu app de autenticación, elige añadir una cuenta y escanea este código con la cámara." }
        Item { width: 1; height: 14; visible: hoja.estado === "configurar" }

        // El QR, sobre blanco para que la cámara lo lea también en tema oscuro.
        Item {
            visible: hoja.estado === "configurar"
            x: 38
            width: parent.width - 38
            height: marcoQr.height
            Rectangle {
                id: marcoQr
                width: 196; height: 196; radius: 14
                color: "white"
                border.color: T.BORDE
                Image {
                    anchors.centerIn: parent
                    width: 184; height: 184
                    source: hoja.c ? hoja.c.qr : ""
                    smooth: false            // módulos nítidos, sin difuminar
                    fillMode: Image.PreserveAspectFit
                }
            }
            Column {
                anchors.left: marcoQr.right
                anchors.leftMargin: 18
                anchors.right: parent.right
                anchors.verticalCenter: marcoQr.verticalCenter
                spacing: 10
                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    lineHeight: 1.25
                    text: "Funciona con Google Authenticator, Microsoft Authenticator, Authy y similares."
                    color: T.TINTA_MEDIA
                    font.family: fuente
                    font.pixelSize: 12
                }
                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: hoja.verClave ? "Ocultar la clave" : "¿No puedes escanearlo? Escribe la clave"
                    color: zonaVerClave.containsMouse ? Qt.lighter(T.ACENTO, 1.15) : T.ACENTO
                    font.family: fuente
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                    MouseArea {
                        id: zonaVerClave
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: hoja.verClave = !hoja.verClave
                    }
                }
            }
        }

        // Clave para escribir a mano (alternativa al QR), plegada por defecto.
        Item { width: 1; height: 12; visible: hoja.estado === "configurar" && hoja.verClave }
        Rectangle {
            visible: hoja.estado === "configurar" && hoja.verClave
            x: 38
            width: parent.width - 38
            height: 56
            radius: 12
            color: oscuro ? T.FONDO : T.ELEVADO
            border.color: T.BORDE
            TextEdit {
                anchors.left: parent.left
                anchors.leftMargin: 16
                anchors.right: copiar.left
                anchors.rightMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                readOnly: true
                selectByMouse: true
                text: hoja.c ? hoja.c.secreto : ""
                color: T.TINTA
                selectionColor: T.ACENTO
                font.family: "Consolas"
                font.pixelSize: 17
                font.letterSpacing: 1
                wrapMode: TextEdit.WrapAnywhere
            }
            Boton {
                id: copiar
                anchors.right: parent.right
                anchors.rightMargin: 8
                anchors.verticalCenter: parent.verticalCenter
                height: 38
                primario: false
                glifo: "\uE8C8"
                texto: "Copiar"
                onPulsado: hoja.c.copiar()
            }
        }

        Item { width: 1; height: 20; visible: hoja.estado === "configurar" }
        Paso { numero: 2; texto: "Escribe el código de 6 dígitos que muestra la app. Se comprueba solo al terminar." }
        Item { width: 1; height: 10; visible: hoja.estado === "configurar" }
        CodigoSeis {
            id: codigo
            visible: hoja.estado === "configurar"
            x: 38
            onCompletado: (valor) => hoja.c.confirmar(valor)
        }
        Item { width: 1; height: 12; visible: hoja.error.length > 0 }
        AvisoError { width: parent.width; mensaje: hoja.error }

        // ---- botones ------------------------------------------------------------
        Item { width: 1; height: 28 }
        Item {
            width: parent.width
            height: 44
            Boton {
                visible: hoja.estado === "activo"
                anchors.left: parent.left
                primario: false
                peligro: true
                texto: "Desactivar"
                onPulsado: hoja.c.desactivar()
            }
            Row {
                anchors.right: parent.right
                spacing: 10
                Boton {
                    primario: false
                    texto: hoja.estado === "configurar" ? "Cancelar" : "Cerrar"
                    onPulsado: puente.cerrarHoja()
                }
                Boton {
                    visible: hoja.estado === "inactivo"
                    glifo: ""
                    texto: "Activar"
                    onPulsado: hoja.c.activar()
                }
                Boton {
                    visible: hoja.estado === "configurar"
                    texto: "Confirmar y activar"
                    onPulsado: {
                        if (codigo.text.length < 6) {
                            hoja.error = "Escribe los 6 dígitos del código."
                            codigo.conError = true
                            codigo.enfocar()
                        } else {
                            hoja.c.confirmar(codigo.text)
                        }
                    }
                }
            }
        }
    }
}
