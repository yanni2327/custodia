// Bitácora de auditoría: quién hizo qué, sobre qué y con qué resultado.
// Solo lectura. A la izquierda los eventos agrupados por día; a la derecha,
// el detalle completo del evento elegido, con el texto seleccionable.
import QtQuick

Item {
    id: hoja

    property var c
    readonly property string titulo: "Bitácora de auditoría"
    readonly property string subtitulo: {
        if (!c) return ""
        const base = c.total + (c.total === 1 ? " evento registrado" : " eventos registrados")
        const neg = c.denegados > 0 ? ", " + c.denegados + (c.denegados === 1 ? " denegado" : " denegados") : ""
        return base + neg + ". Solo lectura: nada de aquí se puede editar ni borrar."
    }
    readonly property int anchoPreferido: 0
    readonly property int altoPreferido: 0

    // ---- filtros ----
    property string texto: ""
    property int iUsuario: 0       // 0 = todos
    property int iOperacion: 0     // 0 = todas
    property string desde: ""      // AAAA-MM-DD; "" = sin límite
    property string hasta: ""
    property int resultado: 0      // 0 todos, 1 denegados, 2 permitidos
    property int elegido: 0
    property var destinoMenu: ""

    readonly property var usuarios: c ? ["Todos"].concat(c.usuarios) : ["Todos"]
    readonly property var operaciones: c ? [{ clave: "", nombre: "Todas" }].concat(c.operaciones) : []
    readonly property var evento: c && elegido >= 0 && elegido < c.eventos.length ? c.eventos[elegido] : null

    function filtrar() {
        if (!c) return
        c.filtrar(texto,
                  iUsuario > 0 ? usuarios[iUsuario] : "",
                  iOperacion > 0 ? operaciones[iOperacion].clave : "",
                  desde, hasta, resultado)
        elegido = 0
        lista.positionViewAtBeginning()
    }
    onTextoChanged: filtrar()
    onIUsuarioChanged: filtrar()
    onIOperacionChanged: filtrar()
    onDesdeChanged: filtrar()
    onHastaChanged: filtrar()
    onResultadoChanged: filtrar()

    function abrirMenu(que, item, nombres, actual) {
        destinoMenu = que
        const p = item.mapToItem(hoja, 0, item.height + 6)
        const ops = nombres.map((n, i) => ({ texto: n, accion: String(i), glifo: i === actual ? "" : "" }))
        menu.abrir(p.x, p.y, ops)
    }

    // ---- barra de filtros ----------------------------------------------------
    Row {
        id: filtros
        width: parent.width
        spacing: 8

        Rectangle {
            width: Math.max(220, filtros.width - otros.width - 8)
            height: 40
            radius: 10
            color: T.CAMPO
            border.color: buscador.activeFocus ? T.ACENTO : T.BORDE
            Behavior on border.color { ColorAnimation { duration: 140 } }
            Text {
                id: lupa
                x: 13
                anchors.verticalCenter: parent.verticalCenter
                text: ""
                font.family: iconos
                font.pixelSize: 13
                color: buscador.activeFocus ? T.ACENTO : T.TINTA_TENUE
            }
            TextInput {
                id: buscador
                anchors.left: lupa.right
                anchors.leftMargin: 10
                anchors.right: parent.right
                anchors.rightMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                clip: true
                color: T.TINTA
                font.family: fuente
                font.pixelSize: 13
                selectByMouse: true
                selectionColor: T.ACENTO
                onTextChanged: hoja.texto = text
                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    visible: buscador.text.length === 0
                    text: "Buscar por usuario, recurso o detalle"
                    color: T.TINTA_TENUE
                    font: buscador.font
                }
            }
        }

        Row {
            id: otros
            spacing: 8
            Desplegable {
                id: dUsuario
                rotulo: "Usuario"
                valor: hoja.usuarios[hoja.iUsuario] || "Todos"
                activo: hoja.iUsuario > 0
                onPulsado: hoja.abrirMenu("usuario", dUsuario, hoja.usuarios, hoja.iUsuario)
            }
            Desplegable {
                id: dOperacion
                rotulo: "Operación"
                valor: hoja.operaciones.length ? hoja.operaciones[hoja.iOperacion].nombre : "Todas"
                activo: hoja.iOperacion > 0
                onPulsado: hoja.abrirMenu("operacion", dOperacion, hoja.operaciones.map(o => o.nombre), hoja.iOperacion)
            }
            Desplegable {
                id: dFecha
                rotulo: "Fecha"
                valor: calendario.describir(hoja.desde, hoja.hasta)
                activo: hoja.desde !== "" || hoja.hasta !== ""
                onPulsado: {
                    const p = dFecha.mapToItem(hoja, dFecha.width, dFecha.height + 8)
                    calendario.x = Math.max(0, Math.min(p.x - calendario.width, hoja.width - calendario.width))
                    calendario.y = p.y
                    calendario.abrir()
                    capaCalendario.abierta = !capaCalendario.abierta
                }
            }

            // Resultado: control segmentado.
            Rectangle {
                height: 40
                width: segmentos.implicitWidth + 8
                radius: 10
                color: T.CAMPO
                border.color: T.BORDE
                Row {
                    id: segmentos
                    anchors.centerIn: parent
                    spacing: 2
                    Repeater {
                        model: ["Todos", "Denegados", "Permitidos"]
                        Rectangle {
                            id: seg
                            required property string modelData
                            required property int index
                            readonly property bool marcado: hoja.resultado === index
                            width: textoSeg.implicitWidth + 24
                            height: 32
                            radius: 8
                            color: marcado ? (index === 1 ? Qt.alpha(T.NEGADO, 0.16)
                                              : index === 2 ? Qt.alpha(T.VERDE, 0.16)
                                              : T.ELEVADO)
                                           : "transparent"
                            Behavior on color { ColorAnimation { duration: 140 } }
                            Text {
                                id: textoSeg
                                anchors.centerIn: parent
                                text: seg.modelData
                                color: !seg.marcado ? T.TINTA_MEDIA
                                     : seg.index === 1 ? T.NEGADO
                                     : seg.index === 2 ? T.VERDE : T.TINTA
                                font.family: fuente
                                font.pixelSize: 13
                                font.weight: seg.marcado ? Font.DemiBold : Font.Normal
                            }
                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.PointingHandCursor
                                onClicked: hoja.resultado = seg.index
                            }
                        }
                    }
                }
            }
        }
    }

    // ---- lista de eventos ----------------------------------------------------
    Rectangle {
        id: marcoLista
        anchors.top: filtros.bottom
        anchors.topMargin: 18
        anchors.left: parent.left
        anchors.right: detalle.left
        anchors.rightMargin: 18
        anchors.bottom: parent.bottom
        radius: 16
        color: "transparent"
        border.color: T.BORDE_SUAVE

        ListView {
            id: lista
            anchors.fill: parent
            anchors.margins: 8
            clip: true
            boundsBehavior: Flickable.StopAtBounds
            model: hoja.c ? hoja.c.eventos : []
            currentIndex: hoja.elegido
            keyNavigationEnabled: true
            focus: true
            onCurrentIndexChanged: hoja.elegido = currentIndex
            section.property: "dia"
            section.criteria: ViewSection.FullString
            section.labelPositioning: ViewSection.InlineLabels | ViewSection.CurrentLabelAtStart
            section.delegate: Rectangle {
                required property string section
                width: ListView.view.width
                height: 36
                color: T.PANEL
                Text {
                    x: 12
                    anchors.verticalCenter: parent.verticalCenter
                    text: parent.section
                    color: T.TINTA_MEDIA
                    font.family: fuente
                    font.pixelSize: 12
                    font.weight: Font.DemiBold
                }
            }

            delegate: Rectangle {
                id: filaEv
                required property var modelData
                required property int index
                readonly property bool elegida: hoja.elegido === index
                width: ListView.view.width
                height: 56
                radius: 10
                color: elegida ? Qt.alpha(T.ACENTO, oscuro ? 0.16 : 0.09)
                     : zonaEv.containsMouse ? T.ELEVADO : "transparent"
                Behavior on color { ColorAnimation { duration: 100 } }

                Rectangle {
                    id: marca
                    x: 12
                    anchors.verticalCenter: parent.verticalCenter
                    width: 30; height: 30; radius: 15
                    color: Qt.alpha(filaEv.modelData.exito ? T.VERDE : T.NEGADO, 0.14)
                    Text {
                        anchors.centerIn: parent
                        text: filaEv.modelData.exito ? "" : ""
                        font.family: iconos
                        font.pixelSize: filaEv.modelData.exito ? 11 : 9
                        color: filaEv.modelData.exito ? T.VERDE : T.NEGADO
                    }
                }
                Column {
                    anchors.left: marca.right
                    anchors.leftMargin: 12
                    anchors.right: derecha.left
                    anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2
                    Text {
                        width: parent.width
                        elide: Text.ElideRight
                        text: filaEv.modelData.operacion
                        color: T.TINTA
                        font.family: fuente
                        font.pixelSize: 14
                        font.weight: Font.DemiBold
                    }
                    Text {
                        width: parent.width
                        elide: Text.ElideMiddle
                        text: filaEv.modelData.ruta || filaEv.modelData.detalle || "Sin recurso"
                        color: T.TINTA_MEDIA
                        font.family: fuente
                        font.pixelSize: 12
                    }
                }
                Column {
                    id: derecha
                    anchors.right: parent.right
                    anchors.rightMargin: 14
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 2
                    Text {
                        anchors.right: parent.right
                        text: filaEv.modelData.usuario || "—"
                        color: T.TINTA
                        font.family: fuente
                        font.pixelSize: 13
                    }
                    Text {
                        anchors.right: parent.right
                        text: filaEv.modelData.hora
                        color: T.TINTA_TENUE
                        font.family: fuente
                        font.pixelSize: 12
                    }
                }
                MouseArea {
                    id: zonaEv
                    anchors.fill: parent
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: { hoja.elegido = filaEv.index; lista.forceActiveFocus() }
                }
            }
        }

        Column {
            visible: hoja.c !== undefined && hoja.c !== null && hoja.c.eventos.length === 0
            anchors.centerIn: parent
            spacing: 6
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Ningún evento coincide"; color: T.TINTA; font.family: fuente; font.pixelSize: 16; font.weight: Font.DemiBold }
            Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Cambia o quita alguno de los filtros."; color: T.TINTA_MEDIA; font.family: fuente; font.pixelSize: 13 }
        }
    }

    // ---- detalle del evento --------------------------------------------------
    Rectangle {
        id: detalle
        width: Math.min(400, hoja.width * 0.38)
        anchors.top: filtros.bottom
        anchors.topMargin: 18
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        radius: 16
        color: oscuro ? T.FONDO : T.ELEVADO
        Behavior on color { ColorAnimation { duration: 260 } }

        Flickable {
            anchors.fill: parent
            anchors.margins: 22
            clip: true
            contentHeight: columnaDet.implicitHeight
            boundsBehavior: Flickable.StopAtBounds
            visible: hoja.evento !== null

            Column {
                id: columnaDet
                width: parent.width
                spacing: 0

                Rectangle {
                    width: 48; height: 48; radius: 15
                    color: Qt.alpha(hoja.evento && hoja.evento.exito ? T.VERDE : T.NEGADO, 0.14)
                    Text {
                        anchors.centerIn: parent
                        text: hoja.evento && hoja.evento.exito ? "" : ""
                        font.family: iconos
                        font.pixelSize: hoja.evento && hoja.evento.exito ? 18 : 15
                        color: hoja.evento && hoja.evento.exito ? T.VERDE : T.NEGADO
                    }
                }
                Item { width: 1; height: 14 }
                Text {
                    width: parent.width
                    wrapMode: Text.WordWrap
                    text: hoja.evento ? hoja.evento.operacion : ""
                    color: T.TINTA
                    font.family: fuente
                    font.pixelSize: 20
                    font.weight: Font.Bold
                }
                Item { width: 1; height: 4 }
                Text {
                    text: hoja.evento ? (hoja.evento.exito ? "Permitido" : "Denegado") : ""
                    color: hoja.evento && hoja.evento.exito ? T.VERDE : T.NEGADO
                    font.family: fuente
                    font.pixelSize: 14
                    font.weight: Font.DemiBold
                }
                Item { width: 1; height: 20 }

                Repeater {
                    model: hoja.evento ? [
                        { r: "Fecha y hora", v: hoja.evento.largo, mono: false },
                        { r: "Usuario", v: hoja.evento.usuario || "—", mono: false },
                        { r: "Recurso", v: hoja.evento.ruta || "—", mono: true },
                        { r: "Detalle", v: hoja.evento.detalle || "—", mono: true },
                        { r: "Código de la operación", v: hoja.evento.accion, mono: true }
                    ] : []
                    Column {
                        id: campo
                        required property var modelData
                        width: columnaDet.width
                        spacing: 4
                        bottomPadding: 16
                        Text {
                            text: campo.modelData.r
                            color: T.TINTA_TENUE
                            font.family: fuente
                            font.pixelSize: 12
                            font.weight: Font.DemiBold
                        }
                        TextEdit {
                            width: parent.width
                            readOnly: true
                            selectByMouse: true
                            wrapMode: TextEdit.WrapAnywhere
                            text: campo.modelData.v
                            color: T.TINTA
                            selectionColor: T.ACENTO
                            font.family: campo.modelData.mono ? "Consolas" : fuente
                            font.pixelSize: 13
                        }
                    }
                }
            }
        }

        Text {
            visible: hoja.evento === null
            anchors.centerIn: parent
            width: parent.width - 60
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            text: "Elige un evento de la lista para ver todos sus datos."
            color: T.TINTA_MEDIA
            font.family: fuente
            font.pixelSize: 13
        }
    }

    MenuFlotante {
        id: menu
        anchoMenu: 240
        onElegido: (accion) => {
            const i = parseInt(accion)
            if (hoja.destinoMenu === "usuario") hoja.iUsuario = i
            else if (hoja.destinoMenu === "operacion") hoja.iOperacion = i
        }
    }

    // ---- calendario (se abre bajo el filtro "Fecha") --------------------------
    Item {
        id: capaCalendario
        property bool abierta: false
        anchors.fill: parent
        z: 900
        visible: abierta || calendario.opacity > 0.01

        MouseArea {
            anchors.fill: parent
            enabled: capaCalendario.abierta
            acceptedButtons: Qt.AllButtons
            onPressed: capaCalendario.abierta = false
        }

        Calendario {
            id: calendario
            desde: hoja.desde
            hasta: hoja.hasta
            diasMarcados: hoja.c ? hoja.c.diasConEventos : []
            opacity: capaCalendario.abierta ? 1 : 0
            scale: capaCalendario.abierta ? 1 : 0.96
            transformOrigin: Item.TopRight
            Behavior on opacity { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
            Behavior on scale { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
            onAplicado: (a, b) => {
                hoja.desde = a
                hoja.hasta = b
                capaCalendario.abierta = false
            }
        }
    }
}
