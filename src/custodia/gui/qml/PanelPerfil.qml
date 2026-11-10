// Panel de la cuenta: se abre desde el avatar de la barra superior.
//
// Sustituye al menú de texto plano. Arriba, quién eres; en medio, el estado
// real de la seguridad de tu cuenta (con acceso directo para cambiarlo) y la
// administración; abajo, bloquear y cerrar sesión.
import QtQuick
import QtQuick.Effects

Item {
    id: panel
    anchors.fill: parent
    z: 1000

    property bool abierto: false
    property real px: 0          // esquina superior derecha del panel
    property real py: 0
    readonly property date inicio: new Date()

    visible: abierto || caja.opacity > 0.01

    function abrir(xDerecha, y) {
        px = xDerecha
        py = y
        puente.refrescarPerfil()
        abierto = true
    }
    function cerrar() { abierto = false }
    function elegir(accion) {
        abierto = false
        puente.accion(accion)
    }

    // Un clic fuera lo cierra.
    MouseArea {
        anchors.fill: parent
        enabled: panel.abierto
        acceptedButtons: Qt.AllButtons
        onPressed: panel.cerrar()
        onWheel: panel.cerrar()
    }

    Rectangle {
        id: caja
        width: 340
        height: columna.implicitHeight
        x: Math.max(8, panel.px - width)
        y: Math.max(8, Math.min(panel.py, panel.height - height - 8))
        radius: 18
        color: T.PANEL
        border.color: T.BORDE
        clip: false

        opacity: panel.abierto ? 1 : 0
        scale: panel.abierto ? 1 : 0.94
        transformOrigin: Item.TopRight
        Behavior on opacity { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
        Behavior on scale { NumberAnimation { duration: 220; easing.type: Easing.OutCubic } }

        layer.enabled: true
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: "#000000"
            shadowOpacity: oscuro ? 0.6 : 0.18
            shadowBlur: 1.0
            blurMax: 44
            shadowVerticalOffset: 12
        }

        MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons }

        Column {
            id: columna
            width: parent.width
            spacing: 0

            // ---- quién eres -------------------------------------------------
            Item {
                width: parent.width
                height: 128

                // Franja de la bóveda, con las esquinas de arriba redondeadas.
                Item {
                    width: parent.width
                    height: 62
                    clip: true
                    Rectangle {
                        width: parent.width
                        height: parent.height + caja.radius
                        radius: caja.radius
                        gradient: Gradient {
                            orientation: Gradient.Horizontal
                            GradientStop { position: 0.0; color: Qt.lighter(T.ACENTO, 1.05) }
                            GradientStop { position: 1.0; color: "#0A1F45" }
                        }
                    }
                    Rectangle {
                        x: parent.width - 90; y: -40
                        width: 120; height: 120; radius: 60
                        color: "white"; opacity: 0.08
                    }
                }
                Rectangle {
                    id: aro
                    x: 20; y: 32
                    width: 60; height: 60; radius: 30
                    color: T.PANEL
                    Image {
                        anchors.centerIn: parent
                        source: "image://iconos/avatar/" + puente.usuario + "?v=" + puente.versionIconos
                        sourceSize: Qt.size(104, 104)
                        width: 52; height: 52
                    }
                }
                Column {
                    anchors.left: aro.right
                    anchors.leftMargin: 12
                    anchors.right: parent.right
                    anchors.rightMargin: 16
                    y: 70
                    spacing: 2
                    Row {
                        spacing: 8
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: puente.usuario
                            color: T.TINTA
                            font.family: fuente
                            font.pixelSize: 17
                            font.weight: Font.Bold
                        }
                        Rectangle {
                            visible: puente.esAdmin
                            anchors.verticalCenter: parent.verticalCenter
                            width: tRol.implicitWidth + 14; height: 20; radius: 10
                            color: Qt.alpha(T.ACENTO, oscuro ? 0.18 : 0.10)
                            Text { id: tRol; anchors.centerIn: parent; text: "Administrador"; color: T.ACENTO; font.family: fuente; font.pixelSize: 11; font.weight: Font.DemiBold }
                        }
                    }
                    Text {
                        text: "Sesión iniciada a las " + Qt.formatTime(panel.inicio, "HH:mm")
                        color: T.TINTA_TENUE
                        font.family: fuente
                        font.pixelSize: 12
                    }
                }
            }

            // ---- seguridad de tu cuenta -----------------------------------------
            Item { width: 1; height: 6 }
            Text {
                x: 20
                text: "Tu cuenta"
                color: T.TINTA_MEDIA
                font.family: fuente
                font.pixelSize: 12
                font.weight: Font.DemiBold
            }
            Item { width: 1; height: 8 }

            Repeater {
                model: [
                    { t: "Verificación en dos pasos", g: "", a: "segundoFactor",
                      si: !!puente.perfil.dosPasos,
                      ok: "Activada: se pide al eliminar, descargar y más",
                      no: "Desactivada: actívala para eliminar o descargar" },
                    { t: "Contraseña", g: "", a: "contrasena", si: true,
                      ok: "Cambiar mi contraseña", no: "", neutra: true }
                ]
                Rectangle {
                    id: fila
                    required property var modelData
                    x: 10
                    width: columna.width - 20
                    height: 52
                    radius: 12
                    color: zonaFila.containsMouse ? T.ELEVADO : "transparent"
                    Behavior on color { ColorAnimation { duration: 120 } }

                    Rectangle {
                        id: icoFila
                        x: 10
                        anchors.verticalCenter: parent.verticalCenter
                        width: 34; height: 34; radius: 10
                        readonly property color tono: fila.modelData.neutra ? T.ACENTO
                                                      : fila.modelData.si ? T.VERDE : "#F59E0B"
                        color: Qt.alpha(tono, 0.14)
                        Text {
                            anchors.centerIn: parent
                            text: fila.modelData.g
                            font.family: iconos
                            font.pixelSize: 14
                            color: parent.tono
                        }
                    }
                    Column {
                        anchors.left: icoFila.right
                        anchors.leftMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 1
                        Text { text: fila.modelData.t; color: T.TINTA; font.family: fuente; font.pixelSize: 13; font.weight: Font.Medium }
                        Text {
                            text: fila.modelData.si ? fila.modelData.ok : fila.modelData.no
                            color: fila.modelData.neutra ? T.TINTA_MEDIA
                                 : fila.modelData.si ? T.VERDE : "#D97706"
                            font.family: fuente
                            font.pixelSize: 12
                        }
                    }
                    Text {
                        anchors.right: parent.right
                        anchors.rightMargin: 12
                        anchors.verticalCenter: parent.verticalCenter
                        text: ""
                        font.family: iconos
                        font.pixelSize: 10
                        color: T.TINTA_TENUE
                    }
                    MouseArea {
                        id: zonaFila
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: panel.elegir(fila.modelData.a)
                    }
                }
            }

            // ---- administración --------------------------------------------------
            Item { width: 1; height: 14 }
            Rectangle { x: 20; width: columna.width - 40; height: 1; color: T.BORDE_SUAVE }
            Item { width: 1; height: 14 }
            Item {
                width: columna.width
                height: 18
                readonly property string volumen: puente.perfil.volumen || ""
                readonly property color tono: volumen === "protegido" ? T.VERDE
                                            : volumen === "sin_proteger" ? "#D97706" : T.TINTA_TENUE
                Text {
                    x: 20
                    anchors.verticalCenter: parent.verticalCenter
                    text: puente.esAdmin ? "Administración" : "Administración (solo administradores)"
                    color: T.TINTA_MEDIA
                    font.family: fuente
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                }
                Text {
                    visible: parent.volumen !== ""
                    anchors.right: parent.right
                    anchors.rightMargin: 20
                    anchors.verticalCenter: parent.verticalCenter
                    text: parent.volumen === "protegido" ? "Volumen protegido"
                        : parent.volumen === "sin_proteger" ? "Volumen sin proteger"
                        : "Volumen sin verificar"
                    color: parent.tono
                    font.family: fuente
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                }
            }
            Item { width: 1; height: 8; visible: !!puente.perfil.volumenAviso }
            Rectangle {
                visible: !!puente.perfil.volumenAviso
                x: 16
                width: columna.width - 32
                height: textoVolumen.implicitHeight + 16
                radius: 10
                color: Qt.alpha("#F59E0B", 0.13)
                border.color: Qt.alpha("#F59E0B", 0.4)
                Text {
                    id: textoVolumen
                    x: 10; y: 8
                    width: parent.width - 20
                    wrapMode: Text.WordWrap
                    text: puente.perfil.volumenAviso || ""
                    color: T.TINTA
                    font.family: fuente
                    font.pixelSize: 11
                }
            }
            Item { width: 1; height: 10 }
            Row {
                x: 16
                spacing: 8
                Repeater {
                    model: [
                        { t: "Cuentas y grupos", d: "Altas y grupos", g: "", a: "cuentas" },
                        { t: "Bitácora", d: "Quién hizo qué", g: "", a: "bitacora" }
                    ]
                    Rectangle {
                        id: tarjeta
                        required property var modelData
                        width: (columna.width - 32 - 8) / 2
                        height: 92
                        radius: 14
                        color: zonaTarjeta.containsMouse ? Qt.alpha(T.ACENTO, oscuro ? 0.14 : 0.08) : (oscuro ? T.FONDO : T.ELEVADO)
                        border.color: zonaTarjeta.containsMouse ? Qt.alpha(T.ACENTO, 0.45) : "transparent"
                        opacity: puente.esAdmin ? 1 : 0.55
                        Behavior on color { ColorAnimation { duration: 140 } }
                        Column {
                            x: 14; y: 14
                            width: parent.width - 28
                            spacing: 8
                            Text {
                                text: tarjeta.modelData.g
                                font.family: iconos
                                font.pixelSize: 18
                                color: T.ACENTO
                            }
                            Column {
                                width: parent.width
                                spacing: 1
                                Text { width: parent.width; elide: Text.ElideRight; text: tarjeta.modelData.t; color: T.TINTA; font.family: fuente; font.pixelSize: 13; font.weight: Font.DemiBold }
                                Text { width: parent.width; elide: Text.ElideRight; text: tarjeta.modelData.d; color: T.TINTA_TENUE; font.family: fuente; font.pixelSize: 11 }
                            }
                        }
                        MouseArea {
                            id: zonaTarjeta
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: panel.elegir(tarjeta.modelData.a)
                        }
                    }
                }
            }

            // ---- respaldo de la clave (solo administradores) ---------------------
            Item { width: 1; height: 6; visible: puente.esAdmin }
            Rectangle {
                id: filaRespaldo
                visible: puente.esAdmin
                x: 16
                width: columna.width - 32
                height: 46
                radius: 12
                color: zonaRespaldo.containsMouse ? Qt.alpha(T.ACENTO, oscuro ? 0.14 : 0.08) : (oscuro ? T.FONDO : T.ELEVADO)
                border.color: zonaRespaldo.containsMouse ? Qt.alpha(T.ACENTO, 0.45) : "transparent"
                Behavior on color { ColorAnimation { duration: 140 } }
                Text {
                    id: icoRespaldo
                    x: 14
                    anchors.verticalCenter: parent.verticalCenter
                    text: ""
                    font.family: iconos
                    font.pixelSize: 16
                    color: T.ACENTO
                }
                Text {
                    anchors.left: icoRespaldo.right
                    anchors.leftMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    text: "Respaldo de la clave"
                    color: T.TINTA
                    font.family: fuente
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }
                MouseArea {
                    id: zonaRespaldo
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: panel.elegir("respaldo")
                }
            }

            // ---- salir -------------------------------------------------------------
            Item { width: 1; height: 16 }
            Rectangle { width: columna.width; height: 1; color: T.BORDE_SUAVE }
            Item {
                width: columna.width
                height: 60
                Row {
                    anchors.left: parent.left
                    anchors.leftMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 4
                    Repeater {
                        model: [
                            { t: "Bloquear", g: "", a: "bloquear", atajo: "Ctrl+L", peligro: false },
                            { t: "Cerrar sesión", g: "", a: "cerrarSesion", atajo: "", peligro: true }
                        ]
                        Rectangle {
                            id: accion
                            required property var modelData
                            height: 38
                            width: filaAccion.implicitWidth + 24
                            radius: 10
                            color: zonaAccion.containsMouse
                                   ? (modelData.peligro ? Qt.alpha(T.NEGADO, 0.12) : T.ELEVADO)
                                   : "transparent"
                            Behavior on color { ColorAnimation { duration: 120 } }
                            Row {
                                id: filaAccion
                                anchors.centerIn: parent
                                spacing: 8
                                Text { anchors.verticalCenter: parent.verticalCenter; text: accion.modelData.g; font.family: iconos; font.pixelSize: 13; color: accion.modelData.peligro ? T.NEGADO : T.TINTA_MEDIA }
                                Text { anchors.verticalCenter: parent.verticalCenter; text: accion.modelData.t; font.family: fuente; font.pixelSize: 13; font.weight: Font.Medium; color: accion.modelData.peligro ? T.NEGADO : T.TINTA }
                                Text { visible: accion.modelData.atajo.length > 0; anchors.verticalCenter: parent.verticalCenter; text: accion.modelData.atajo; font.family: fuente; font.pixelSize: 11; color: T.TINTA_TENUE }
                            }
                            MouseArea {
                                id: zonaAccion
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: panel.elegir(accion.modelData.a)
                            }
                        }
                    }
                }
            }
        }
    }
}
