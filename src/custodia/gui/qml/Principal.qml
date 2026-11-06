// Ventana principal de Custodia.
//
// Concepto: la bóveda. La barra lateral lleva el mismo azul del inicio de
// sesión y la carpeta abierta "sale" de ella como una pestaña del color del
// contenido. Es el único gesto llamativo; el resto es sobrio a propósito.
//
// Los datos llegan de Python por `puente` (arbol, archivos, vista, cabecera,
// panel, seleccion, rutaActual, modal, bloqueo) y las acciones vuelven por
// puente.accion(), puente.abrir() y puente.seleccionar(). Esta vista no decide
// nada sobre permisos: dibuja lo que Python le da.
import QtQuick
import QtQuick.Effects

Rectangle {
    id: raiz
    color: T.FONDO
    Behavior on color { ColorAnimation { duration: 260 } }

    // ---- estado de la vista ------------------------------------------------

    property string filtro: ""
    property var expandidas: ({ "/": true })
    readonly property bool bloqueado: !!puente.bloqueo.activo
    readonly property bool ocupada: bloqueado || !!puente.modal.tipo || puente.hoja !== ""

    readonly property var seleccionado: {
        for (const a of puente.archivos)
            if (a.ruta === puente.seleccion) return a
        return null
    }
    readonly property var archivosFiltrados: {
        const f = filtro.trim().toLowerCase()
        if (!f) return puente.archivos
        return puente.archivos.filter(a => a.nombre.toLowerCase().indexOf(f) >= 0)
    }
    readonly property int cifrados: puente.archivos.filter(a => a.cifrado).length
    readonly property var arbolVisible:
        puente.arbol.filter(f => ancestros(f.ruta).every(a => raiz.expandidas[a]))

    function cerrarMenus() { menu.cerrar(); panelPerfil.cerrar() }

    function ancestros(ruta) {
        if (ruta === "/") return []
        const partes = ruta.split("/").filter(p => p.length > 0)
        const res = ["/"]
        let acc = ""
        for (let i = 0; i < partes.length - 1; i++) {
            acc += "/" + partes[i]
            res.push(acc)
        }
        return res
    }
    function alternarRama(ruta) {
        const e = Object.assign({}, expandidas)
        e[ruta] = !e[ruta]
        expandidas = e
    }

    function opcionesElemento(a) {
        const ops = []
        if (a.esCarpeta) ops.push({ texto: "Abrir", glifo: "", accion: "abrir" })
        else ops.push({ texto: "Guardar una copia…", glifo: "", accion: "descargar" })
        ops.push({ texto: "Renombrar…", glifo: "", accion: "renombrar", atajo: "F2" })
        ops.push({ texto: "Permisos…", glifo: "", accion: "permisos" })
        ops.push({ separador: true })
        ops.push({ texto: "Eliminar", glifo: "", accion: "eliminar", peligro: true, atajo: "Supr" })
        return ops
    }

    // Al entrar en una carpeta: desplegar su rama, limpiar la búsqueda y
    // animar la llegada del contenido.
    Connections {
        target: puente
        function onRutaActualChanged() {
            const e = Object.assign({}, raiz.expandidas)
            for (const a of raiz.ancestros(puente.rutaActual)) e[a] = true
            e[puente.rutaActual] = true
            raiz.expandidas = e
            raiz.filtro = ""
            buscador.text = ""
            animCarpeta.restart()
        }
        function onNotificacion(texto) { aviso.mostrar(texto) }
    }

    // ---- atajos de teclado (apagados con la pantalla bloqueada o un aviso) ---

    Shortcut { sequence: "Delete"; enabled: !raiz.ocupada && raiz.seleccionado !== null; onActivated: puente.accion("eliminar") }
    Shortcut { sequence: "F2"; enabled: !raiz.ocupada && raiz.seleccionado !== null; onActivated: puente.accion("renombrar") }
    Shortcut { sequence: "Ctrl+Shift+N"; enabled: !raiz.ocupada; onActivated: puente.accion("nuevaCarpeta") }
    Shortcut { sequence: "Ctrl+F"; enabled: !raiz.ocupada; onActivated: buscador.forceActiveFocus() }
    Shortcut { sequence: "Esc"; enabled: !raiz.ocupada; onActivated: { menu.cerrar(); panelPerfil.cerrar(); puente.seleccionar("", false) } }
    // Esc también cierra la hoja abierta (si no hay un aviso encima).
    Shortcut {
        sequence: "Esc"
        enabled: puente.hoja !== "" && !puente.modal.tipo && !raiz.bloqueado
        onActivated: puente.cerrarHoja()
    }

    // =========================================================================
    //  APLICACIÓN (lo que se desenfoca detrás de un aviso)
    // =========================================================================
    Item {
        id: app
        anchors.fill: parent

        // Fondo propio: el desenfoque del aviso parte de esta capa y, sin
        // fondo, dejaría huecos transparentes por los que se vería el
        // contenido nítido de debajo.
        Rectangle {
            anchors.fill: parent
            color: T.FONDO
            Behavior on color { ColorAnimation { duration: 260 } }
        }

        // Barra lateral y área de trabajo: lo que se desenfoca detrás de una
        // hoja abierta.
        Item {
        id: base
        anchors.fill: parent

        // ================== LA BÓVEDA (barra lateral) ==================
        Item {
            id: lateral
            width: 264
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.left: parent.left
            clip: true

            Rectangle {
                anchors.fill: parent
                gradient: Gradient {
                    GradientStop { position: 0.0; color: Qt.lighter(T.ACENTO, 1.05) }
                    GradientStop { position: 0.55; color: T.ACENTO_HONDO }
                    GradientStop { position: 1.0; color: "#0A1F45" }
                }
            }
            Repeater {
                model: [
                    { x: -90, y: -70, d: 280, dx: 22, dy: 16, t: 9000 },
                    { x: 120, y: 520, d: 320, dx: -18, dy: -24, t: 12000 }
                ]
                Rectangle {
                    required property var modelData
                    width: modelData.d; height: modelData.d; radius: width / 2
                    x: modelData.x; y: modelData.y
                    color: "white"
                    opacity: 0.06
                    SequentialAnimation on x {
                        loops: Animation.Infinite
                        NumberAnimation { to: modelData.x + modelData.dx; duration: modelData.t; easing.type: Easing.InOutSine }
                        NumberAnimation { to: modelData.x; duration: modelData.t; easing.type: Easing.InOutSine }
                    }
                    SequentialAnimation on y {
                        loops: Animation.Infinite
                        NumberAnimation { to: modelData.y + modelData.dy; duration: modelData.t * 1.3; easing.type: Easing.InOutSine }
                        NumberAnimation { to: modelData.y; duration: modelData.t * 1.3; easing.type: Easing.InOutSine }
                    }
                }
            }

            // Marca.
            Row {
                id: marca
                x: 22
                y: 22
                spacing: 12
                Rectangle {
                    width: 40; height: 40; radius: 11
                    color: "white"
                    Image { anchors.centerIn: parent; source: logoUrl; width: 26; height: 26; mipmap: true }
                }
                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 0
                    Text { text: "Custodia"; color: "white"; font.family: fuente; font.pixelSize: 18; font.weight: Font.Bold }
                    Text { text: "Almacén seguro"; color: Qt.alpha("white", 0.62); font.family: fuente; font.pixelSize: 12 }
                }
            }

            Text {
                id: rotuloCarpetas
                x: 24
                anchors.top: marca.bottom
                anchors.topMargin: 32
                text: "Carpetas"
                color: Qt.alpha("white", 0.6)
                font.family: fuente
                font.pixelSize: 12
                font.weight: Font.DemiBold
            }

            ListView {
                id: arbolVista
                anchors.top: rotuloCarpetas.bottom
                anchors.topMargin: 10
                anchors.left: parent.left
                anchors.leftMargin: 12
                anchors.right: parent.right
                anchors.bottom: chip.top
                anchors.bottomMargin: 14
                clip: true
                spacing: 2
                boundsBehavior: Flickable.StopAtBounds
                model: raiz.arbolVisible
                currentIndex: {
                    const l = raiz.arbolVisible
                    for (let i = 0; i < l.length; i++)
                        if (l[i].ruta === puente.rutaActual) return i
                    return -1
                }
                highlightFollowsCurrentItem: true
                highlightMoveDuration: 260
                highlightMoveVelocity: -1
                highlightResizeDuration: 0

                // La pestaña: del color del contenido, pegada al borde derecho,
                // con las esquinas cóncavas que la unen al área de trabajo.
                highlight: Item {
                    Rectangle {
                        anchors.fill: parent
                        radius: 12
                        color: T.FONDO
                        Behavior on color { ColorAnimation { duration: 260 } }
                    }
                    Rectangle {
                        anchors.right: parent.right
                        width: 14
                        height: parent.height
                        color: T.FONDO
                    }
                    Canvas {
                        id: esquinaArriba
                        width: 12; height: 12
                        anchors.right: parent.right
                        anchors.bottom: parent.top
                        property color c: T.FONDO
                        onCChanged: requestPaint()
                        onPaint: {
                            const g = getContext("2d")
                            g.reset()
                            g.fillStyle = c
                            g.beginPath()
                            g.moveTo(12, 0); g.lineTo(12, 12); g.lineTo(0, 12)
                            g.arc(0, 0, 12, Math.PI / 2, 0, true)
                            g.closePath(); g.fill()
                        }
                    }
                    Canvas {
                        width: 12; height: 12
                        anchors.right: parent.right
                        anchors.top: parent.bottom
                        property color c: T.FONDO
                        onCChanged: requestPaint()
                        onPaint: {
                            const g = getContext("2d")
                            g.reset()
                            g.fillStyle = c
                            g.beginPath()
                            g.moveTo(12, 12); g.lineTo(12, 0); g.lineTo(0, 0)
                            g.arc(0, 12, 12, -Math.PI / 2, 0, false)
                            g.closePath(); g.fill()
                        }
                    }
                }

                // Hueco arriba para que la esquina superior de la primera
                // pestaña no quede recortada.
                header: Item { width: 1; height: 12 }

                delegate: Item {
                    id: nodo
                    required property var modelData
                    required property int index
                    readonly property bool actual: puente.rutaActual === modelData.ruta
                    readonly property bool abierta: !!raiz.expandidas[modelData.ruta]
                    width: ListView.view.width
                    height: 40

                    Rectangle {
                        anchors.fill: parent
                        anchors.rightMargin: 12
                        radius: 10
                        color: Qt.alpha("white", zonaNodo.containsMouse && !nodo.actual ? 0.09 : 0)
                        Behavior on color { ColorAnimation { duration: 120 } }
                    }
                    MouseArea {
                        id: zonaNodo
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: puente.abrir(nodo.modelData.ruta)
                        onDoubleClicked: if (nodo.modelData.hijos) raiz.alternarRama(nodo.modelData.ruta)
                    }

                    Row {
                        x: 10 + nodo.modelData.nivel * 14
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 8

                        Item {
                            width: 14; height: 14
                            anchors.verticalCenter: parent.verticalCenter
                            Text {
                                anchors.centerIn: parent
                                visible: nodo.modelData.hijos
                                text: ""
                                font.family: iconos
                                font.pixelSize: 9
                                color: nodo.actual ? T.TINTA_TENUE : Qt.alpha("white", 0.6)
                                rotation: nodo.abierta ? 90 : 0
                                Behavior on rotation { NumberAnimation { duration: 160; easing.type: Easing.OutCubic } }
                            }
                            MouseArea {
                                anchors.fill: parent
                                anchors.margins: -5
                                enabled: nodo.modelData.hijos
                                cursorShape: Qt.PointingHandCursor
                                onClicked: raiz.alternarRama(nodo.modelData.ruta)
                            }
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: nodo.modelData.nivel === 0 ? "" : ""
                            font.family: iconos
                            font.pixelSize: 15
                            color: nodo.actual ? T.ACENTO : Qt.alpha("white", 0.85)
                            Behavior on color { ColorAnimation { duration: 200 } }
                        }
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            width: arbolVista.width - 70 - nodo.modelData.nivel * 14
                            elide: Text.ElideRight
                            text: nodo.modelData.nombre
                            color: nodo.actual ? T.TINTA : Qt.alpha("white", 0.9)
                            font.family: fuente
                            font.pixelSize: 14
                            font.weight: nodo.actual ? Font.DemiBold : Font.Normal
                            Behavior on color { ColorAnimation { duration: 200 } }
                        }
                    }
                }
            }

            // Cuenta, sobre un cristal claro.
            Rectangle {
                id: chip
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.margins: 14
                height: 64
                radius: 14
                color: Qt.alpha("white", 0.1)
                border.color: Qt.alpha("white", 0.14)

                Image {
                    id: avatarChip
                    x: 12
                    anchors.verticalCenter: parent.verticalCenter
                    source: "image://iconos/avatar/" + puente.usuario + "?v=" + puente.versionIconos
                    sourceSize: Qt.size(80, 80)
                    width: 38; height: 38
                }
                Column {
                    anchors.left: avatarChip.right
                    anchors.leftMargin: 11
                    anchors.right: salir.left
                    anchors.rightMargin: 6
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 1
                    Text { width: parent.width; elide: Text.ElideRight; text: puente.usuario; color: "white"; font.family: fuente; font.pixelSize: 14; font.weight: Font.DemiBold }
                    Text { text: puente.esAdmin ? "Administrador" : "Usuario"; color: Qt.alpha("white", 0.62); font.family: fuente; font.pixelSize: 12 }
                }
                Rectangle {
                    id: salir
                    anchors.right: parent.right
                    anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    width: 34; height: 34; radius: 10
                    color: Qt.alpha("white", zonaSalir.containsMouse ? 0.16 : 0)
                    Behavior on color { ColorAnimation { duration: 120 } }
                    Text { anchors.centerIn: parent; text: ""; font.family: iconos; font.pixelSize: 15; color: "white" }
                    MouseArea {
                        id: zonaSalir
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: puente.accion("cerrarSesion")
                    }
                }
            }
        }

        // ================== ÁREA DE TRABAJO ==================
        Item {
            id: trabajo
            anchors.left: lateral.right
            anchors.right: parent.right
            anchors.top: parent.top
            anchors.bottom: parent.bottom
            anchors.leftMargin: 32
            anchors.rightMargin: 28

            // ---- barra superior: migas, búsqueda, tema, perfil ----
            Item {
                id: barra
                z: 5
                anchors.left: parent.left
                anchors.right: parent.right
                y: 18
                height: 44

                Row {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 8
                    Repeater {
                        model: puente.cabecera.migas || []
                        Row {
                            id: miga
                            required property var modelData
                            required property int index
                            readonly property bool ultima: index === (puente.cabecera.migas.length - 1)
                            spacing: 8
                            Text {
                                visible: miga.index > 0
                                anchors.verticalCenter: parent.verticalCenter
                                text: ""
                                font.family: iconos
                                font.pixelSize: 9
                                color: T.TINTA_TENUE
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: miga.modelData.nombre
                                font.family: fuente
                                font.pixelSize: 13
                                font.weight: miga.ultima ? Font.DemiBold : Font.Normal
                                color: miga.ultima ? T.TINTA : (zonaMiga.containsMouse ? T.ACENTO : T.TINTA_MEDIA)
                                Behavior on color { ColorAnimation { duration: 120 } }
                                MouseArea {
                                    id: zonaMiga
                                    anchors.fill: parent
                                    anchors.margins: -4
                                    hoverEnabled: true
                                    enabled: !miga.ultima
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: puente.abrir(miga.modelData.ruta)
                                }
                            }
                        }
                    }
                }

                Row {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 8

                    Rectangle {
                        width: 250
                        height: 40
                        radius: 20
                        color: T.PANEL
                        border.width: 1
                        border.color: buscador.activeFocus ? T.ACENTO : T.BORDE
                        Behavior on border.color { ColorAnimation { duration: 140 } }

                        Text {
                            id: lupa
                            x: 15
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
                            anchors.right: limpiar.left
                            anchors.rightMargin: 8
                            anchors.verticalCenter: parent.verticalCenter
                            clip: true
                            color: T.TINTA
                            font.family: fuente
                            font.pixelSize: 13
                            selectByMouse: true
                            selectionColor: T.ACENTO
                            onTextChanged: raiz.filtro = text
                            Keys.onEscapePressed: { text = ""; focus = false }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                visible: buscador.text.length === 0
                                text: "Buscar en esta carpeta"
                                color: T.TINTA_TENUE
                                font: buscador.font
                            }
                        }
                        Text {
                            id: limpiar
                            anchors.right: parent.right
                            anchors.rightMargin: 15
                            anchors.verticalCenter: parent.verticalCenter
                            text: buscador.text.length > 0 ? "" : "Ctrl+F"
                            font.family: buscador.text.length > 0 ? iconos : fuente
                            font.pixelSize: 10
                            color: T.TINTA_TENUE
                            MouseArea {
                                anchors.fill: parent
                                anchors.margins: -6
                                enabled: buscador.text.length > 0
                                cursorShape: Qt.PointingHandCursor
                                onClicked: buscador.text = ""
                            }
                        }
                    }

                    IconoBoton {
                        lado: 40
                        radius: 20
                        glifo: oscuro ? "" : ""
                        pista: oscuro ? "Tema claro" : "Tema oscuro"
                        onPulsado: puente.accion("tema")
                    }

                    Rectangle {
                        id: perfil
                        width: 58; height: 40; radius: 20
                        color: zonaPerfil.containsMouse || panelPerfil.abierto ? T.ELEVADO : "transparent"
                        Behavior on color { ColorAnimation { duration: 120 } }
                        Row {
                            anchors.centerIn: parent
                            spacing: 5
                            Image {
                                anchors.verticalCenter: parent.verticalCenter
                                source: "image://iconos/avatar/" + puente.usuario + "?v=" + puente.versionIconos
                                sourceSize: Qt.size(64, 64)
                                width: 30; height: 30
                            }
                            Text {
                                anchors.verticalCenter: parent.verticalCenter
                                text: ""
                                font.family: iconos
                                font.pixelSize: 9
                                color: T.TINTA_MEDIA
                            }
                        }
                        MouseArea {
                            id: zonaPerfil
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: {
                                const p = perfil.mapToItem(raiz, perfil.width, perfil.height + 8)
                                panelPerfil.abrir(p.x, p.y)
                            }
                        }
                    }
                }
            }

            // ---- título de la carpeta y acciones para crear ----
            Item {
                id: titulo
                anchors.top: barra.bottom
                anchors.topMargin: 26
                anchors.left: parent.left
                anchors.right: parent.right
                height: 62

                Column {
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 4
                    Text {
                        text: puente.cabecera.titulo || ""
                        color: T.TINTA
                        font.family: fuente
                        font.pixelSize: 32
                        font.weight: Font.Bold
                        font.letterSpacing: -0.5
                    }
                    Row {
                        spacing: 14
                        Text {
                            text: puente.cabecera.subtitulo || ""
                            color: T.TINTA_MEDIA
                            font.family: fuente
                            font.pixelSize: 14
                        }
                        Row {
                            visible: raiz.cifrados > 0
                            spacing: 5
                            Text { text: ""; font.family: iconos; font.pixelSize: 11; color: T.VERDE; anchors.verticalCenter: parent.verticalCenter }
                            Text {
                                text: raiz.cifrados === 1 ? "1 cifrado" : raiz.cifrados + " cifrados"
                                color: T.VERDE
                                font.family: fuente
                                font.pixelSize: 14
                                font.weight: Font.Medium
                            }
                        }
                    }
                }

                Row {
                    anchors.right: parent.right
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 10
                    Boton { primario: false; glifo: ""; texto: "Nueva carpeta"; onPulsado: puente.accion("nuevaCarpeta") }
                    Boton { glifo: ""; texto: "Añadir archivos"; onPulsado: puente.accion("subir") }
                }
            }

            // ---- listado y ficha ----
            Item {
                id: cuerpo
                anchors.top: titulo.bottom
                anchors.topMargin: 22
                anchors.left: parent.left
                anchors.right: parent.right
                anchors.bottom: parent.bottom
                anchors.bottomMargin: 26

                // ======== listado ========
                Rectangle {
                    id: tarjetaLista
                    anchors.left: parent.left
                    anchors.right: ficha.left
                    anchors.rightMargin: 20
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    radius: 18
                    color: T.PANEL
                    border.color: T.BORDE_SUAVE
                    Behavior on color { ColorAnimation { duration: 260 } }

                    Item {
                        id: contenidoLista
                        anchors.fill: parent
                        property real dy: 0
                        transform: Translate { y: contenidoLista.dy }

                        ParallelAnimation {
                            id: animCarpeta
                            NumberAnimation { target: contenidoLista; property: "opacity"; from: 0; to: 1; duration: 260; easing.type: Easing.OutCubic }
                            NumberAnimation { target: contenidoLista; property: "dy"; from: 12; to: 0; duration: 320; easing.type: Easing.OutCubic }
                        }

                        readonly property int anchoTamano: 96
                        readonly property int anchoFecha: 170

                        // Encabezados de columna.
                        Item {
                            id: columnas
                            visible: puente.vista.modo === "lista"
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.leftMargin: 24
                            anchors.rightMargin: 24
                            height: 46
                            Text { x: 50; anchors.verticalCenter: parent.verticalCenter; text: "Nombre"; color: T.TINTA_TENUE; font.family: fuente; font.pixelSize: 12; font.weight: Font.DemiBold }
                            Text { x: parent.width - contenidoLista.anchoFecha - contenidoLista.anchoTamano; anchors.verticalCenter: parent.verticalCenter; text: "Tamaño"; color: T.TINTA_TENUE; font.family: fuente; font.pixelSize: 12; font.weight: Font.DemiBold }
                            Text { x: parent.width - contenidoLista.anchoFecha; anchors.verticalCenter: parent.verticalCenter; text: "Modificado"; color: T.TINTA_TENUE; font.family: fuente; font.pixelSize: 12; font.weight: Font.DemiBold }
                        }

                        // Clic en el hueco vacío = quitar la selección.
                        MouseArea {
                            anchors.fill: lista
                            onClicked: puente.seleccionar("", false)
                        }

                        ListView {
                            id: lista
                            visible: puente.vista.modo === "lista"
                            anchors.top: columnas.bottom
                            anchors.left: parent.left
                            anchors.right: parent.right
                            anchors.bottom: parent.bottom
                            anchors.leftMargin: 10
                            anchors.rightMargin: 10
                            anchors.bottomMargin: 10
                            clip: true
                            spacing: 2
                            boundsBehavior: Flickable.StopAtBounds
                            model: raiz.archivosFiltrados

                            delegate: Item {
                                id: fila
                                required property var modelData
                                required property int index
                                readonly property bool elegida: puente.seleccion === modelData.ruta
                                width: ListView.view.width
                                height: 54

                                // Entrada escalonada al cargar la carpeta.
                                opacity: 0
                                property real dx: 10
                                transform: Translate { x: fila.dx }
                                Component.onCompleted: entrada.start()
                                SequentialAnimation {
                                    id: entrada
                                    PauseAnimation { duration: Math.min(fila.index, 12) * 24 }
                                    ParallelAnimation {
                                        NumberAnimation { target: fila; property: "opacity"; to: 1; duration: 220; easing.type: Easing.OutCubic }
                                        NumberAnimation { target: fila; property: "dx"; to: 0; duration: 280; easing.type: Easing.OutCubic }
                                    }
                                }

                                Rectangle {
                                    anchors.fill: parent
                                    radius: 12
                                    color: fila.elegida ? Qt.alpha(T.ACENTO, oscuro ? 0.16 : 0.09)
                                         : zonaFila.containsMouse ? T.ELEVADO : "transparent"
                                    Behavior on color { ColorAnimation { duration: 120 } }
                                }

                                FichaTipo {
                                    id: tipoFila
                                    x: 14
                                    anchors.verticalCenter: parent.verticalCenter
                                    lado: 36
                                    esCarpeta: fila.modelData.esCarpeta
                                    ext: fila.modelData.ext
                                    cifrado: fila.modelData.cifrado
                                }
                                Text {
                                    anchors.left: tipoFila.right
                                    anchors.leftMargin: 14
                                    anchors.right: tamanoFila.left
                                    anchors.rightMargin: 16
                                    anchors.verticalCenter: parent.verticalCenter
                                    elide: Text.ElideRight
                                    text: fila.modelData.nombre
                                    color: T.TINTA
                                    font.family: fuente
                                    font.pixelSize: 14
                                    font.weight: fila.modelData.esCarpeta || fila.elegida ? Font.DemiBold : Font.Normal
                                }
                                Text {
                                    id: tamanoFila
                                    x: fila.width - 14 - contenidoLista.anchoFecha - contenidoLista.anchoTamano
                                    width: contenidoLista.anchoTamano
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: fila.modelData.tamano
                                    color: T.TINTA_MEDIA
                                    font.family: fuente
                                    font.pixelSize: 13
                                }
                                Text {
                                    x: fila.width - 14 - contenidoLista.anchoFecha
                                    width: contenidoLista.anchoFecha
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: fila.modelData.modificado
                                    color: T.TINTA_MEDIA
                                    font.family: fuente
                                    font.pixelSize: 13
                                }

                                MouseArea {
                                    id: zonaFila
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    acceptedButtons: Qt.LeftButton | Qt.RightButton
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: (ev) => {
                                        puente.seleccionar(fila.modelData.ruta, fila.modelData.esCarpeta)
                                        if (ev.button === Qt.RightButton) {
                                            const p = fila.mapToItem(raiz, ev.x, ev.y)
                                            menu.abrir(p.x, p.y, raiz.opcionesElemento(fila.modelData))
                                        }
                                    }
                                    onDoubleClicked: if (fila.modelData.esCarpeta) puente.abrir(fila.modelData.ruta)
                                }
                            }
                        }

                        // Búsqueda sin resultados.
                        Column {
                            visible: puente.vista.modo === "lista" && raiz.archivosFiltrados.length === 0
                            anchors.centerIn: parent
                            spacing: 8
                            Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Nada coincide con «" + raiz.filtro + "»"; color: T.TINTA; font.family: fuente; font.pixelSize: 16; font.weight: Font.DemiBold }
                            Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Prueba con otra palabra o borra la búsqueda."; color: T.TINTA_MEDIA; font.family: fuente; font.pixelSize: 13 }
                        }

                        // Estado vacío: carpeta vacía, protegida o con error.
                        Column {
                            id: vacio
                            visible: puente.vista.modo === "vacia"
                            anchors.centerIn: parent
                            width: 400
                            spacing: 0

                            readonly property var estilo: ({
                                "carpeta": { color: T.ACENTO, glifo: "" },
                                "candado": { color: "#F59E0B", glifo: "" },
                                "error":   { color: T.NEGADO, glifo: "" },
                                "info":    { color: T.ACENTO, glifo: "" }
                            })[puente.vista.tipo || "info"] || ({ color: T.ACENTO, glifo: "" })

                            Rectangle {
                                anchors.horizontalCenter: parent.horizontalCenter
                                width: 76; height: 76; radius: 24
                                color: Qt.alpha(vacio.estilo.color, 0.13)
                                Text {
                                    anchors.centerIn: parent
                                    text: vacio.estilo.glifo
                                    font.family: iconos
                                    font.pixelSize: 30
                                    color: vacio.estilo.color
                                }
                            }
                            Item { width: 1; height: 20 }
                            Text {
                                width: parent.width
                                horizontalAlignment: Text.AlignHCenter
                                text: puente.vista.titulo || ""
                                color: T.TINTA
                                font.family: fuente
                                font.pixelSize: 20
                                font.weight: Font.Bold
                            }
                            Item { width: 1; height: 8 }
                            Text {
                                width: parent.width
                                horizontalAlignment: Text.AlignHCenter
                                wrapMode: Text.WordWrap
                                lineHeight: 1.3
                                text: puente.vista.texto || ""
                                color: T.TINTA_MEDIA
                                font.family: fuente
                                font.pixelSize: 14
                            }
                            Item { width: 1; height: 24; visible: !!puente.vista.acciones }
                            Row {
                                visible: !!puente.vista.acciones
                                anchors.horizontalCenter: parent.horizontalCenter
                                spacing: 10
                                Boton { primario: false; glifo: ""; texto: "Nueva carpeta"; onPulsado: puente.accion("nuevaCarpeta") }
                                Boton { glifo: ""; texto: "Añadir archivos"; onPulsado: puente.accion("subir") }
                            }
                        }
                    }

                    // Arrastrar archivos desde el Explorador.
                    DropArea {
                        id: zonaSoltar
                        anchors.fill: parent
                        onEntered: (ev) => { if (!ev.hasUrls) ev.accepted = false }
                        onDropped: (ev) => {
                            if (ev.hasUrls) {
                                puente.soltarArchivos(ev.urls)
                                ev.acceptProposedAction()
                            }
                        }
                    }
                    Rectangle {
                        anchors.fill: parent
                        anchors.margins: 6
                        radius: 14
                        color: Qt.alpha(T.ACENTO, 0.08)
                        border.color: T.ACENTO
                        border.width: 2
                        opacity: zonaSoltar.containsDrag ? 1 : 0
                        visible: opacity > 0
                        Behavior on opacity { NumberAnimation { duration: 140 } }
                        Column {
                            anchors.centerIn: parent
                            spacing: 10
                            Text { anchors.horizontalCenter: parent.horizontalCenter; text: ""; font.family: iconos; font.pixelSize: 34; color: T.ACENTO }
                            Text { anchors.horizontalCenter: parent.horizontalCenter; text: "Suelta para añadir a «" + (puente.cabecera.titulo || "") + "»"; color: T.ACENTO; font.family: fuente; font.pixelSize: 15; font.weight: Font.DemiBold }
                        }
                    }
                }

                // ======== ficha del elemento ========
                Rectangle {
                    id: ficha
                    width: 300
                    anchors.right: parent.right
                    anchors.top: parent.top
                    anchors.bottom: parent.bottom
                    radius: 18
                    color: T.PANEL
                    border.color: T.BORDE_SUAVE
                    Behavior on color { ColorAnimation { duration: 260 } }

                    readonly property var el: raiz.seleccionado
                    readonly property bool esCarpeta: el === null || el.esCarpeta

                    Flickable {
                        id: desplFicha
                        anchors.fill: parent
                        anchors.margins: 1
                        clip: true
                        boundsBehavior: Flickable.StopAtBounds
                        contentWidth: width
                        contentHeight: Math.max(height, contenidoFicha.implicitHeight + pieFicha.implicitHeight + 20 * 2 + 8)

                        Column {
                            id: contenidoFicha
                            x: 22
                            y: 20
                            width: desplFicha.width - 44
                            spacing: 0

                            // Cambia con un fundido breve al elegir otro elemento.
                            NumberAnimation on opacity { id: animFicha; from: 0.3; to: 1; duration: 220; easing.type: Easing.OutCubic; running: false }
                            Connections { target: puente; function onPanelChanged() { animFicha.restart() } }

                            FichaTipo {
                                lado: 48
                                esCarpeta: ficha.esCarpeta
                                ext: ficha.el ? ficha.el.ext : ""
                                cifrado: ficha.el ? ficha.el.cifrado : false
                            }
                            Item { width: 1; height: 12 }
                            Text {
                                width: parent.width
                                wrapMode: Text.WrapAnywhere
                                maximumLineCount: 3
                                elide: Text.ElideRight
                                text: puente.panel.elemento || ""
                                color: T.TINTA
                                font.family: fuente
                                font.pixelSize: 18
                                font.weight: Font.Bold
                            }
                            Item { width: 1; height: 4 }
                            Text {
                                width: parent.width
                                text: {
                                    if (!ficha.el) return "Carpeta actual"
                                    if (ficha.el.esCarpeta) return "Carpeta"
                                    const t = ficha.el.ext ? "Archivo " + ficha.el.ext.toUpperCase() : "Archivo"
                                    return t + ", " + ficha.el.tamano + (ficha.el.cifrado ? ", cifrado" : "")
                                }
                                color: T.TINTA_MEDIA
                                font.family: fuente
                                font.pixelSize: 13
                            }

                            Item { width: 1; height: 14 }
                            Text { text: "Propietario"; color: T.TINTA_TENUE; font.family: fuente; font.pixelSize: 12; font.weight: Font.DemiBold }
                            Item { width: 1; height: 4 }
                            Text {
                                width: parent.width
                                wrapMode: Text.WrapAnywhere
                                text: puente.panel.propietario || ""
                                color: T.TINTA
                                font.family: fuente
                                font.pixelSize: 13
                            }

                            Item { width: 1; height: 14 }
                            Text { text: "Lo que puedes hacer aquí"; color: T.TINTA_TENUE; font.family: fuente; font.pixelSize: 12; font.weight: Font.DemiBold }
                            Item { width: 1; height: 10 }

                            // Indicadores, no botones: quien concede o niega es
                            // el sistema; aquí solo se muestra el resultado.
                            Flow {
                                width: parent.width
                                spacing: 6
                                Repeater {
                                    model: puente.panel.permisos || []
                                    Rectangle {
                                        id: chipPermiso
                                        required property var modelData
                                        readonly property bool si: modelData.concedido
                                        height: 30
                                        width: filaChip.implicitWidth + 22
                                        radius: 15
                                        color: si ? Qt.alpha(T.ACENTO, oscuro ? 0.16 : 0.10) : "transparent"
                                        border.width: si ? 0 : 1
                                        border.color: T.BORDE
                                        Behavior on color { ColorAnimation { duration: 200 } }
                                        Row {
                                            id: filaChip
                                            anchors.centerIn: parent
                                            spacing: 6
                                            Text {
                                                anchors.verticalCenter: parent.verticalCenter
                                                text: chipPermiso.si ? "" : ""
                                                font.family: iconos
                                                font.pixelSize: chipPermiso.si ? 10 : 8
                                                color: chipPermiso.si ? T.ACENTO : T.TINTA_TENUE
                                            }
                                            Text {
                                                anchors.verticalCenter: parent.verticalCenter
                                                text: chipPermiso.modelData.etiqueta
                                                color: chipPermiso.si ? T.TINTA : T.TINTA_TENUE
                                                font.family: fuente
                                                font.pixelSize: 12
                                                font.weight: chipPermiso.si ? Font.Medium : Font.Normal
                                            }
                                        }
                                    }
                                }
                            }
                        }

                        // Acciones sobre el elemento, siempre debajo del contenido.
                        Column {
                            id: pieFicha
                            x: 13
                            width: desplFicha.width - 26
                            y: desplFicha.contentHeight - implicitHeight - 13
                            spacing: 2

                            Rectangle { x: 10; width: parent.width - 20; height: 1; color: T.BORDE_SUAVE }
                            Item { width: 1; height: 6 }

                            Repeater {
                                model: {
                                    if (!ficha.el) return [{ t: "Permisos de esta carpeta…", g: "", a: "permisos" }]
                                    const ops = []
                                    if (!ficha.el.esCarpeta) ops.push({ t: "Guardar una copia…", g: "", a: "descargar" })
                                    else ops.push({ t: "Abrir", g: "", a: "abrir" })
                                    ops.push({ t: "Renombrar…", g: "", a: "renombrar" })
                                    ops.push({ t: "Permisos…", g: "", a: "permisos" })
                                    ops.push({ t: "Eliminar", g: "", a: "eliminar", peligro: true })
                                    return ops
                                }
                                Rectangle {
                                    id: accionFicha
                                    required property var modelData
                                    width: pieFicha.width
                                    height: 36
                                    radius: 10
                                    color: zonaAccion.containsMouse
                                           ? (modelData.peligro ? Qt.alpha(T.NEGADO, 0.12) : T.ELEVADO)
                                           : "transparent"
                                    Behavior on color { ColorAnimation { duration: 120 } }
                                    readonly property color tinta: modelData.peligro ? T.NEGADO : T.TINTA
                                    Text {
                                        x: 12
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: accionFicha.modelData.g
                                        font.family: iconos
                                        font.pixelSize: 14
                                        color: accionFicha.modelData.peligro ? T.NEGADO : T.TINTA_MEDIA
                                    }
                                    Text {
                                        x: 40
                                        anchors.verticalCenter: parent.verticalCenter
                                        text: accionFicha.modelData.t
                                        font.family: fuente
                                        font.pixelSize: 13
                                        font.weight: Font.Medium
                                        color: accionFicha.tinta
                                    }
                                    MouseArea {
                                        id: zonaAccion
                                        anchors.fill: parent
                                        hoverEnabled: true
                                        cursorShape: Qt.PointingHandCursor
                                        onClicked: {
                                            if (accionFicha.modelData.a === "abrir") puente.abrir(puente.seleccion)
                                            else puente.accion(accionFicha.modelData.a)
                                        }
                                    }
                                }
                            }
                        }
                    }

                    // Indicador de desplazamiento, solo si hace falta.
                    Rectangle {
                        visible: desplFicha.contentHeight > desplFicha.height + 8
                        anchors.right: parent.right
                        anchors.rightMargin: 4
                        width: 4
                        radius: 2
                        color: T.TINTA_TENUE
                        opacity: desplFicha.moving ? 0.8 : 0.35
                        Behavior on opacity { NumberAnimation { duration: 200 } }
                        y: 8 + (desplFicha.height - 16) * desplFicha.visibleArea.yPosition
                        height: (desplFicha.height - 16) * desplFicha.visibleArea.heightRatio
                    }
                }
            }
        }
        }

        // Hojas de administración (cuentas, bitácora, permisos…). Van dentro
        // de `app` para que un aviso abierto encima también las desenfoque.
        CapaHojas { fondo: base }
    }

    // =========================================================================
    //  CAPAS SUPERIORES
    // =========================================================================

    // Confirmación breve tras una acción. Responde a lo que la persona hizo.
    Rectangle {
        id: aviso
        z: 800
        anchors.horizontalCenter: parent.horizontalCenter
        anchors.horizontalCenterOffset: lateral.width / 2
        y: parent.height - (abierto ? height + 28 : -10)
        width: filaAviso.implicitWidth + 36
        height: 46
        radius: 23
        color: oscuro ? "#F2F4F7" : "#14181F"
        opacity: abierto ? 1 : 0
        property bool abierto: false
        property string texto: ""
        Behavior on y { NumberAnimation { duration: 320; easing.type: Easing.OutBack; easing.overshoot: 1.2 } }
        Behavior on opacity { NumberAnimation { duration: 200 } }
        function mostrar(t) { texto = t; abierto = true; temporizador.restart() }
        Timer { id: temporizador; interval: 2800; onTriggered: aviso.abierto = false }
        Row {
            id: filaAviso
            anchors.centerIn: parent
            spacing: 10
            Rectangle {
                width: 22; height: 22; radius: 11
                color: T.VERDE
                anchors.verticalCenter: parent.verticalCenter
                Text { anchors.centerIn: parent; text: ""; font.family: iconos; font.pixelSize: 10; color: "white" }
            }
            Text {
                anchors.verticalCenter: parent.verticalCenter
                text: aviso.texto
                color: oscuro ? "#0F1720" : "white"
                font.family: fuente
                font.pixelSize: 14
                font.weight: Font.Medium
            }
        }
    }

    MenuFlotante {
        id: menu
        objectName: "menu"
        onElegido: (accion) => {
            if (accion === "abrir") puente.abrir(puente.seleccion)
            else puente.accion(accion)
        }
    }

    PanelPerfil {
        id: panelPerfil
        objectName: "panelPerfil"
    }

    Modal { fondo: app }

    Bloqueo { }
}
