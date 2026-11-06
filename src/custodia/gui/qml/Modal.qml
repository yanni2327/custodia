// Avisos, confirmaciones y preguntas dentro de la ventana principal.
//
// Python los pide a través de `puente.modal` (ver avisos.py y
// VentanaPrincipal.preguntar) y espera la respuesta, que vuelve con
// puente.responder({ ok, texto }). El contenido de la ventana queda detrás,
// desenfocado y oscurecido, para que quede claro qué está esperando respuesta.
import QtQuick
import QtQuick.Effects

Item {
    id: modal
    anchors.fill: parent
    z: 900

    property Item fondo
    property var d: ({})
    property bool abierto: false
    property int elegida: 0

    visible: abierto || capa.opacity > 0.01

    readonly property var estilos: ({
        "info":        { color: T.ACENTO, glifo: "" },
        "exito":       { color: T.VERDE, glifo: "" },
        "advertencia": { color: "#F59E0B", glifo: "" },
        "error":       { color: T.NEGADO, glifo: "" },
        "pregunta":    { color: T.ACENTO, glifo: "" },
        "texto":       { color: T.ACENTO, glifo: "" },
        "opcion":      { color: T.ACENTO, glifo: "" },
        "codigo":      { color: T.ACENTO, glifo: "" },
        "secreto":     { color: T.ACENTO, glifo: "" }
    })
    readonly property var est: {
        if (d.tipo === "texto" && d.password) return { color: T.ACENTO, glifo: "" }
        if (d.tipo === "codigo" && d.peligro) return { color: T.NEGADO, glifo: "" }
        return estilos[d.tipo] || estilos["info"]
    }

    property real sacudida: 0
    SequentialAnimation {
        id: animSacudida
        NumberAnimation { target: modal; property: "sacudida"; to: -10; duration: 45 }
        NumberAnimation { target: modal; property: "sacudida"; to: 9; duration: 70 }
        NumberAnimation { target: modal; property: "sacudida"; to: -6; duration: 65 }
        NumberAnimation { target: modal; property: "sacudida"; to: 3; duration: 60 }
        NumberAnimation { target: modal; property: "sacudida"; to: 0; duration: 55 }
    }

    Connections {
        target: puente
        function onModalChanged() {
            // Mismo código pedido otra vez (el anterior no valía): la ventana
            // no se cierra; se avisa, se sacude y se vacían las casillas.
            if (modal.abierto && puente.modal.tipo === "codigo" && modal.d.tipo === "codigo") {
                modal.d = puente.modal
                codigoModal.limpiar()
                codigoModal.conError = true
                animSacudida.restart()
                codigoModal.enfocar()
                return
            }
            if (puente.modal.tipo) {
                modal.d = puente.modal
                modal.elegida = puente.modal.actual || 0
                campo.text = puente.modal.valor || ""
                campo.mostrar = false
                modal.abierto = true
                enfocar.restart()
            } else {
                modal.abierto = false
            }
        }
    }

    Timer {
        id: enfocar
        interval: 40
        onTriggered: {
            if (modal.d.tipo === "texto") {
                campo.enfocar()
                campo.entrada.selectAll()
            } else if (modal.d.tipo === "codigo") {
                codigoModal.limpiar()
                codigoModal.conError = false
                codigoModal.enfocar()
            } else {
                caja.forceActiveFocus()
            }
        }
    }

    function responder(ok) {
        if (!abierto) return
        let texto = ""
        if (d.tipo === "texto") texto = campo.text
        else if (d.tipo === "opcion") texto = d.opciones[elegida]
        else if (d.tipo === "codigo") texto = codigoModal.text
        if (ok && d.tipo === "codigo" && texto.length < 6) {
            codigoModal.conError = true
            codigoModal.enfocar()
            animSacudida.restart()
            return
        }
        if (ok && d.tipo === "texto" && texto.trim().length === 0) {
            campo.conError = true
            campo.enfocar()
            return
        }
        puente.responder({ ok: ok, texto: texto })
    }

    // ---- fondo: la ventana desenfocada y oscurecida ------------------------
    MultiEffect {
        anchors.fill: parent
        source: modal.visible ? modal.fondo : null
        blurEnabled: true
        blur: 1.0
        blurMax: 40
        autoPaddingEnabled: false
        opacity: capa.opacity
        visible: modal.visible && modal.fondo !== null
    }
    Rectangle {
        id: capa
        anchors.fill: parent
        color: Qt.alpha("#05070C", oscuro ? 0.55 : 0.32)
        opacity: modal.abierto ? 1 : 0
        Behavior on opacity { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
    }
    // Nada de lo de detrás responde mientras hay una pregunta abierta.
    MouseArea {
        anchors.fill: parent
        enabled: modal.abierto
        hoverEnabled: true
        acceptedButtons: Qt.AllButtons
        onWheel: (ev) => ev.accepted = true
    }

    // ---- tarjeta -------------------------------------------------------------
    Rectangle {
        id: caja
        width: 460
        height: columna.implicitHeight + 56
        anchors.centerIn: parent
        radius: 20
        color: T.PANEL
        border.color: T.BORDE
        focus: modal.abierto

        opacity: modal.abierto ? 1 : 0
        scale: modal.abierto ? 1 : 0.94
        Behavior on opacity { NumberAnimation { duration: 180; easing.type: Easing.OutCubic } }
        Behavior on scale { NumberAnimation { duration: 240; easing.type: Easing.OutBack; easing.overshoot: 1.2 } }

        layer.enabled: true
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: "#000000"
            shadowOpacity: oscuro ? 0.6 : 0.2
            shadowBlur: 1.0
            blurMax: 48
            shadowVerticalOffset: 16
        }

        transform: Translate { x: modal.sacudida }

        Keys.onEscapePressed: modal.responder(false)
        Keys.onReturnPressed: modal.responder(true)
        Keys.onEnterPressed: modal.responder(true)
        Keys.onUpPressed: if (modal.d.tipo === "opcion") modal.elegida = Math.max(0, modal.elegida - 1)
        Keys.onDownPressed: if (modal.d.tipo === "opcion") modal.elegida = Math.min(modal.d.opciones.length - 1, modal.elegida + 1)

        Column {
            id: columna
            x: 28
            y: 28
            width: parent.width - 56
            spacing: 0

            Row {
                width: parent.width
                spacing: 14
                Rectangle {
                    width: 44; height: 44; radius: 14
                    color: Qt.alpha(modal.est.color, 0.14)
                    Text {
                        anchors.centerIn: parent
                        text: modal.est.glifo
                        font.family: iconos
                        font.pixelSize: 19
                        color: modal.est.color
                    }
                }
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width - 58
                    wrapMode: Text.WordWrap
                    text: modal.d.titulo || ""
                    color: T.TINTA
                    font.family: fuente
                    font.pixelSize: 19
                    font.weight: Font.Bold
                }
            }

            Item { width: 1; height: 14; visible: texto.visible }
            Text {
                id: texto
                visible: (modal.d.mensaje || "").length > 0
                width: parent.width
                wrapMode: Text.WordWrap
                lineHeight: 1.3
                text: modal.d.mensaje || ""
                color: T.TINTA_MEDIA
                font.family: fuente
                font.pixelSize: 14
            }

            Item { width: 1; height: 18; visible: campo.visible }
            Campo {
                id: campo
                visible: modal.d.tipo === "texto"
                width: parent.width
                rotulo: modal.d.etiqueta || ""
                icono: modal.d.password ? "" : ""
                esPassword: !!modal.d.password
                onAceptado: modal.responder(true)
                onTeclaSoltada: conError = false
            }

            // Dato para copiar o dictar (p. ej. una contraseña temporal).
            Item { width: 1; height: 18; visible: cajaSecreto.visible }
            Rectangle {
                id: cajaSecreto
                visible: modal.d.tipo === "secreto"
                width: parent.width
                height: 64
                radius: 12
                color: oscuro ? T.FONDO : T.ELEVADO
                border.color: T.BORDE
                TextEdit {
                    anchors.left: parent.left
                    anchors.leftMargin: 18
                    anchors.right: botonCopiar.left
                    anchors.rightMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    readOnly: true
                    selectByMouse: true
                    text: modal.d.secreto || ""
                    color: T.TINTA
                    selectionColor: T.ACENTO
                    font.family: "Consolas"
                    font.pixelSize: 22
                    font.letterSpacing: 1.5
                }
                Boton {
                    id: botonCopiar
                    anchors.right: parent.right
                    anchors.rightMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    height: 40
                    primario: false
                    glifo: ""
                    texto: "Copiar"
                    onPulsado: puente.copiarTexto(modal.d.secreto || "")
                }
            }

            // Código de la app de autenticación: se envía solo al completarse.
            Item { width: 1; height: 20; visible: codigoModal.visible }
            Item {
                visible: modal.d.tipo === "codigo"
                width: parent.width
                height: codigoModal.height
                CodigoSeis {
                    id: codigoModal
                    anchors.horizontalCenter: parent.horizontalCenter
                    onCompletado: modal.responder(true)
                }
            }
            Item { width: 1; height: 12; visible: !!modal.d.error }
            AvisoError { width: parent.width; mensaje: modal.d.tipo === "codigo" ? (modal.d.error || "") : "" }

            Item { width: 1; height: 18; visible: opciones.visible }
            Column {
                id: opciones
                visible: modal.d.tipo === "opcion"
                width: parent.width
                spacing: 6
                Text {
                    visible: (modal.d.etiqueta || "").length > 0
                    text: modal.d.etiqueta || ""
                    color: T.TINTA_MEDIA
                    font.family: fuente
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                    bottomPadding: 2
                }
                // Con muchas opciones la lista se desplaza (rueda o flechas) en
                // lugar de crecer hasta salirse de la pantalla.
                Item {
                    width: parent.width
                    height: listaOpciones.height
                ListView {
                    id: listaOpciones
                    width: parent.width
                    height: Math.min(contentHeight, Math.max(150, modal.height - 360))
                    clip: true
                    spacing: 6
                    boundsBehavior: Flickable.StopAtBounds
                    model: modal.d.tipo === "opcion" ? modal.d.opciones : []
                    currentIndex: modal.elegida
                    highlightFollowsCurrentItem: false
                    onCurrentIndexChanged: positionViewAtIndex(currentIndex, ListView.Contain)
                    delegate: Rectangle {
                        id: op
                        required property string modelData
                        required property int index
                        readonly property bool marcada: modal.elegida === index
                        width: listaOpciones.width
                        height: 42
                        radius: 10
                        color: marcada ? Qt.alpha(T.ACENTO, 0.12)
                             : zonaOp.containsMouse ? T.ELEVADO : "transparent"
                        border.color: marcada ? T.ACENTO : T.BORDE
                        Behavior on color { ColorAnimation { duration: 120 } }
                        Behavior on border.color { ColorAnimation { duration: 120 } }
                        Rectangle {
                            x: 14
                            anchors.verticalCenter: parent.verticalCenter
                            width: 16; height: 16; radius: 8
                            color: "transparent"
                            border.width: op.marcada ? 5 : 1.5
                            border.color: op.marcada ? T.ACENTO : T.TINTA_TENUE
                            Behavior on border.width { NumberAnimation { duration: 120 } }
                        }
                        Text {
                            x: 42
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width - 56
                            elide: Text.ElideRight
                            text: op.modelData
                            color: T.TINTA
                            font.family: fuente
                            font.pixelSize: 14
                        }
                        MouseArea {
                            id: zonaOp
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: modal.elegida = op.index
                            onDoubleClicked: { modal.elegida = op.index; modal.responder(true) }
                        }
                    }
                }
                // Barra de desplazamiento, solo si hay más opciones que hueco.
                Rectangle {
                    visible: listaOpciones.contentHeight > listaOpciones.height + 1
                    anchors.right: parent.right
                    anchors.rightMargin: -10
                    width: 4
                    radius: 2
                    color: T.TINTA_TENUE
                    opacity: listaOpciones.moving ? 0.85 : 0.45
                    Behavior on opacity { NumberAnimation { duration: 200 } }
                    y: listaOpciones.height * listaOpciones.visibleArea.yPosition
                    height: listaOpciones.height * listaOpciones.visibleArea.heightRatio
                }
                }
            }

            Item { width: 1; height: 26 }
            Item {
                width: parent.width
                height: 44
                Row {
                    anchors.right: parent.right
                    spacing: 10
                    Boton {
                        visible: (modal.d.cancelar || "").length > 0
                        primario: false
                        texto: modal.d.cancelar || ""
                        onPulsado: modal.responder(false)
                    }
                    Boton {
                        texto: modal.d.aceptar || "Aceptar"
                        peligro: !!modal.d.peligro
                        onPulsado: modal.responder(true)
                    }
                }
            }
        }
    }
}
