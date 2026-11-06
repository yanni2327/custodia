// Inicio de sesión de Custodia.
//
// Ventana sin marco del sistema: una tarjeta con sombra y dos columnas. A la
// izquierda, la marca sobre un degradado con formas que flotan despacio; a la
// derecha, el formulario. El paso del segundo factor entra deslizándose desde
// la derecha en la misma tarjeta, sin abrir otra ventana.
//
// Toda la lógica está en Python (`puente`): esta vista solo recoge datos y
// reacciona a las señales error / pideCodigo / exito / ocupadoCambio.
import QtQuick
import QtQuick.Effects
import QtQuick.Window

Window {
    id: win
    width: 960
    height: 620
    visible: false
    title: "Custodia — Iniciar sesión"
    color: "transparent"
    flags: Qt.Window | Qt.FramelessWindowHint

    property bool pideCodigo: false
    property bool pideNueva: false     // contraseña temporal: crear una nueva
    readonly property bool enCredenciales: !pideCodigo && !pideNueva
    property bool ocupado: false
    property bool mayus: false
    property string error: ""
    property real sacudida: 0

    readonly property color ambar: "#F59E0B"

    onClosing: puente.cancelar()
    onVisibleChanged: if (visible) animEntrada.start()
    onActiveChanged: if (active) win.mayus = puente.mayusculas()

    function entrar() {
        if (win.ocupado) return
        if (campoUsuario.text.trim().length === 0) {
            mostrarError("Escribe el nombre de la cuenta.")
            campoUsuario.enfocar()
            return
        }
        if (campoPassword.text.length === 0) {
            mostrarError("Escribe tu contraseña.")
            campoPassword.enfocar()
            return
        }
        win.error = ""
        puente.entrar(campoUsuario.text, campoPassword.text)
    }

    function verificar() {
        if (win.ocupado) return
        if (entradaCodigo.text.length !== 6) {
            mostrarError("Escribe los 6 dígitos del código.")
            entradaCodigo.forceActiveFocus()
            return
        }
        win.error = ""
        puente.verificarCodigo(entradaCodigo.text)
    }

    function cambiarContrasena() {
        if (win.ocupado) return
        if (nueva1.text.length === 0) {
            mostrarError("Escribe tu contraseña nueva.")
            nueva1.enfocar()
            return
        }
        if (nueva1.text !== nueva2.text) {
            mostrarError("Las dos contraseñas no coinciden.")
            nueva2.text = ""
            nueva2.enfocar()
            return
        }
        win.error = ""
        puente.cambiarContrasena(nueva1.text, nueva2.text)
    }

    function volver() {
        if (win.ocupado) return
        puente.volver()
        win.error = ""
        win.pideCodigo = false
        win.pideNueva = false
        nueva1.text = ""
        nueva2.text = ""
        campoPassword.text = ""
        campoPassword.enfocar()
    }

    function mostrarError(mensaje) {
        win.error = mensaje
        animSacudida.restart()
    }

    Connections {
        target: puente
        function onError(mensaje) {
            win.mostrarError(mensaje)
            if (win.pideCodigo) {
                entradaCodigo.text = ""
                entradaCodigo.forceActiveFocus()
            } else if (win.pideNueva) {
                nueva2.text = ""
                nueva1.enfocar()
            } else {
                campoPassword.text = ""
                campoPassword.enfocar()
            }
        }
        function onPideNuevaContrasena() {
            win.error = ""
            win.pideCodigo = false
            win.pideNueva = true
            nueva1.text = ""
            nueva2.text = ""
            nueva1.enfocar()
        }
        function onPideCodigo() {
            win.error = ""
            win.pideNueva = false
            win.pideCodigo = true
            entradaCodigo.text = ""
            entradaCodigo.forceActiveFocus()
        }
        function onExito() { animSalida.start() }
        function onOcupadoCambio(valor) { win.ocupado = valor }
    }

    Shortcut {
        sequence: "Esc"
        onActivated: win.enCredenciales ? win.close() : win.volver()
    }

    // ---- animaciones de la ventana ----------------------------------------

    ParallelAnimation {
        id: animEntrada
        NumberAnimation { target: escena; property: "opacity"; from: 0; to: 1; duration: 380; easing.type: Easing.OutCubic }
        NumberAnimation { target: escena; property: "scale"; from: 0.95; to: 1; duration: 460; easing.type: Easing.OutBack; easing.overshoot: 1.1 }
        NumberAnimation { target: escena; property: "desplazamiento"; from: 16; to: 0; duration: 460; easing.type: Easing.OutCubic }
        onFinished: campoUsuario.enfocar()
    }

    ParallelAnimation {
        id: animSalida
        NumberAnimation { target: escena; property: "opacity"; to: 0; duration: 240; easing.type: Easing.InCubic }
        NumberAnimation { target: escena; property: "scale"; to: 0.97; duration: 240; easing.type: Easing.InCubic }
        onFinished: puente.terminar()
    }

    SequentialAnimation {
        id: animSacudida
        NumberAnimation { target: win; property: "sacudida"; to: -10; duration: 45 }
        NumberAnimation { target: win; property: "sacudida"; to: 9; duration: 70 }
        NumberAnimation { target: win; property: "sacudida"; to: -6; duration: 65 }
        NumberAnimation { target: win; property: "sacudida"; to: 3; duration: 60 }
        NumberAnimation { target: win; property: "sacudida"; to: 0; duration: 55 }
    }

    // ---- escena --------------------------------------------------------------

    Item {
        id: escena
        anchors.fill: parent
        anchors.margins: 36
        opacity: 0
        property real desplazamiento: 0
        transform: Translate { y: escena.desplazamiento }

        // Sombra suave bajo la tarjeta.
        Rectangle {
            anchors.fill: tarjeta
            radius: tarjeta.radius
            color: T.PANEL
            layer.enabled: true
            layer.effect: MultiEffect {
                shadowEnabled: true
                shadowColor: "#000000"
                shadowOpacity: oscuro ? 0.7 : 0.22
                shadowBlur: 1.0
                blurMax: 48
                shadowVerticalOffset: 14
            }
        }

        Rectangle {
            id: tarjeta
            anchors.fill: parent
            radius: 18
            color: T.PANEL
            border.color: T.BORDE
            border.width: 1

            // ================= columna de la marca =================
            Item {
                id: marca
                width: 400
                anchors.top: parent.top
                anchors.bottom: parent.bottom
                anchors.left: parent.left
                clip: true   // recorta las esquinas derechas del degradado

                DragHandler {
                    target: null
                    onActiveChanged: if (active) win.startSystemMove()
                }

                Rectangle {
                    width: parent.width + tarjeta.radius
                    height: parent.height
                    radius: tarjeta.radius
                    gradient: Gradient {
                        GradientStop { position: 0.0; color: Qt.lighter(T.ACENTO, 1.05) }
                        GradientStop { position: 0.55; color: T.ACENTO_HONDO }
                        GradientStop { position: 1.0; color: "#0A1F45" }
                    }
                }

                // Formas que flotan: dan vida sin distraer.
                Repeater {
                    model: [
                        { x: -70, y: -50, d: 260, dx: 26, dy: 18, t: 7000 },
                        { x: 230, y: 330, d: 300, dx: -22, dy: -26, t: 9000 },
                        { x: 260, y: 30, d: 120, dx: -16, dy: 22, t: 6000 }
                    ]
                    Rectangle {
                        required property var modelData
                        width: modelData.d; height: modelData.d; radius: width / 2
                        x: modelData.x; y: modelData.y
                        color: "white"
                        opacity: 0.07
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

                // Marca arriba.
                Row {
                    x: 40; y: 40
                    spacing: 12
                    Rectangle {
                        width: 44; height: 44; radius: 12
                        color: "white"
                        Image {
                            anchors.centerIn: parent
                            source: logoUrl
                            width: 30; height: 30
                            smooth: true
                            mipmap: true
                        }
                    }
                    Column {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 1
                        Text { text: "Custodia"; color: "white"; font.family: fuente; font.pixelSize: 19; font.weight: Font.Bold }
                        Text { text: "ALMACÉN SEGURO"; color: Qt.alpha("white", 0.65); font.family: fuente; font.pixelSize: 10; font.letterSpacing: 1.6; font.weight: Font.DemiBold }
                    }
                }

                // Mensaje central.
                Column {
                    x: 40
                    width: parent.width - 80
                    anchors.verticalCenter: parent.verticalCenter
                    anchors.verticalCenterOffset: 20
                    spacing: 14

                    Text {
                        width: parent.width
                        text: "Tus archivos,\nbajo llave."
                        color: "white"
                        font.family: fuente
                        font.pixelSize: 34
                        font.weight: Font.Bold
                        lineHeight: 1.05
                    }
                    // Texto neutro a propósito: esta pantalla la ve cualquiera,
                    // también quien no tiene cuenta, así que no describe cómo
                    // está protegido el sistema.
                    Text {
                        id: lema
                        width: parent.width
                        wrapMode: Text.WordWrap
                        text: "Inicia sesión para acceder a tu espacio de trabajo."
                        color: Qt.alpha("white", 0.75)
                        font.family: fuente
                        font.pixelSize: 15
                        lineHeight: 1.25
                        opacity: 0
                        property real dy: 8
                        transform: Translate { y: lema.dy }
                        SequentialAnimation {
                            running: escena.opacity > 0.5
                            PauseAnimation { duration: 180 }
                            ParallelAnimation {
                                NumberAnimation { target: lema; property: "opacity"; to: 1; duration: 360; easing.type: Easing.OutCubic }
                                NumberAnimation { target: lema; property: "dy"; to: 0; duration: 360; easing.type: Easing.OutCubic }
                            }
                        }
                    }
                }

                Text {
                    x: 40
                    anchors.bottom: parent.bottom
                    anchors.bottomMargin: 30
                    text: "Acceso solo para cuentas autorizadas"
                    color: Qt.alpha("white", 0.5)
                    font.family: fuente
                    font.pixelSize: 12
                }
            }

            // ================= columna del formulario =================
            Item {
                id: lado
                anchors.left: marca.right
                anchors.right: parent.right
                anchors.top: parent.top
                anchors.bottom: parent.bottom

                // Franja superior para arrastrar la ventana.
                Item {
                    anchors.left: parent.left
                    anchors.right: controles.left
                    anchors.top: parent.top
                    height: 56
                    DragHandler {
                        target: null
                        onActiveChanged: if (active) win.startSystemMove()
                    }
                }

                // Minimizar y cerrar.
                Row {
                    id: controles
                    anchors.top: parent.top
                    anchors.right: parent.right
                    anchors.margins: 14
                    spacing: 4
                    Repeater {
                        model: [{ g: "", cerrar: false }, { g: "", cerrar: true }]
                        Rectangle {
                            required property var modelData
                            width: 34; height: 30; radius: 8
                            color: zonaCtl.containsMouse
                                   ? (modelData.cerrar ? T.NEGADO : T.ELEVADO) : "transparent"
                            Behavior on color { ColorAnimation { duration: 120 } }
                            Text {
                                anchors.centerIn: parent
                                text: modelData.g
                                font.family: iconos
                                font.pixelSize: 10
                                color: zonaCtl.containsMouse && modelData.cerrar ? "white" : T.TINTA_MEDIA
                            }
                            MouseArea {
                                id: zonaCtl
                                anchors.fill: parent
                                hoverEnabled: true
                                onClicked: modelData.cerrar ? win.close() : win.showMinimized()
                            }
                        }
                    }
                }

                // Contenedor de los dos pasos, que se deslizan entre sí.
                Item {
                    id: pasos
                    width: 360
                    height: 420
                    anchors.centerIn: parent
                    clip: false
                    transform: Translate { x: win.sacudida }

                    // ---------- paso 1: credenciales ----------
                    Column {
                        id: pasoCredenciales
                        width: parent.width
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 16
                        x: win.enCredenciales ? 0 : -60
                        opacity: win.enCredenciales ? 1 : 0
                        visible: opacity > 0
                        enabled: win.enCredenciales
                        Behavior on x { NumberAnimation { duration: 340; easing.type: Easing.OutCubic } }
                        Behavior on opacity { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }

                        Column {
                            spacing: 6
                            Text { text: "Bienvenido"; color: T.TINTA; font.family: fuente; font.pixelSize: 30; font.weight: Font.Bold }
                            Text { text: "Inicia sesión para continuar."; color: T.TINTA_MEDIA; font.family: fuente; font.pixelSize: 14 }
                        }
                        Item { width: 1; height: 6 }

                        Campo {
                            id: campoUsuario
                            width: parent.width
                            rotulo: "Usuario"
                            marcador: "Nombre de la cuenta"
                            icono: ""
                            onAceptado: campoPassword.enfocar()
                        }
                        Campo {
                            id: campoPassword
                            width: parent.width
                            rotulo: "Contraseña"
                            marcador: "Tu contraseña"
                            icono: ""
                            esPassword: true
                            conError: win.error.length > 0 && win.enCredenciales
                            onAceptado: win.entrar()
                            onTeclaSoltada: win.mayus = puente.mayusculas()
                            onFocoCambiado: win.mayus = puente.mayusculas()
                        }

                        // Aviso de Bloq Mayús.
                        Row {
                            spacing: 8
                            visible: opacity > 0
                            opacity: win.mayus && campoPassword.entrada.activeFocus ? 1 : 0
                            height: opacity > 0 ? implicitHeight : 0
                            Behavior on opacity { NumberAnimation { duration: 160 } }
                            Text { text: ""; font.family: iconos; font.pixelSize: 13; color: win.ambar; anchors.verticalCenter: parent.verticalCenter }
                            Text { text: "Bloq Mayús está activado"; color: win.ambar; font.family: fuente; font.pixelSize: 12; font.weight: Font.DemiBold }
                        }

                        AvisoError { width: parent.width; mensaje: win.enCredenciales ? win.error : "" }

                        Item { width: 1; height: 2 }
                        Boton {
                            width: parent.width
                            texto: "Entrar"
                            ocupado: win.ocupado
                            onPulsado: win.entrar()
                        }
                        Text {
                            width: parent.width
                            horizontalAlignment: Text.AlignHCenter
                            wrapMode: Text.WordWrap
                            text: "¿No puedes entrar? Pide ayuda a un administrador del equipo."
                            color: T.TINTA_TENUE
                            font.family: fuente
                            font.pixelSize: 12
                        }
                    }

                    // ---------- paso 2: segundo factor ----------
                    Column {
                        id: pasoCodigo
                        width: parent.width
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 16
                        x: win.pideCodigo ? 0 : 60
                        opacity: win.pideCodigo ? 1 : 0
                        visible: opacity > 0
                        enabled: win.pideCodigo
                        Behavior on x { NumberAnimation { duration: 340; easing.type: Easing.OutCubic } }
                        Behavior on opacity { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }

                        // Volver.
                        Item {
                        width: filaVolver.implicitWidth
                        height: filaVolver.implicitHeight
                        Row {
                            id: filaVolver
                            spacing: 6
                            opacity: zonaVolver.containsMouse ? 1 : 0.75
                            Text { text: ""; font.family: iconos; font.pixelSize: 12; color: T.ACENTO; anchors.verticalCenter: parent.verticalCenter }
                            Text { text: "Volver"; color: T.ACENTO; font.family: fuente; font.pixelSize: 13; font.weight: Font.DemiBold }
                        }
                        MouseArea {
                            id: zonaVolver
                            anchors.fill: parent
                            anchors.margins: -6
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: win.volver()
                        }
                        }

                        Rectangle {
                            width: 52; height: 52; radius: 14
                            color: Qt.alpha(T.ACENTO, 0.14)
                            Text { anchors.centerIn: parent; text: ""; font.family: iconos; font.pixelSize: 22; color: T.ACENTO }
                        }

                        Column {
                            width: parent.width
                            spacing: 6
                            Text { text: "Verificación en dos pasos"; color: T.TINTA; font.family: fuente; font.pixelSize: 24; font.weight: Font.Bold }
                            Text {
                                width: parent.width
                                wrapMode: Text.WordWrap
                                text: "Escribe el código de 6 dígitos que muestra tu app de autenticación."
                                color: T.TINTA_MEDIA
                                font.family: fuente
                                font.pixelSize: 14
                            }
                        }

                        // Seis casillas para el código.
                        Item {
                            width: parent.width
                            height: 58

                            TextInput {
                                id: entradaCodigo
                                width: 1; height: 1
                                opacity: 0
                                maximumLength: 6
                                inputMethodHints: Qt.ImhDigitsOnly
                                validator: RegularExpressionValidator { regularExpression: /[0-9]{0,6}/ }
                                onTextChanged: {
                                    if (text.length > 0) win.error = ""
                                    if (text.length === 6) win.verificar()
                                }
                                onAccepted: win.verificar()
                            }

                            Row {
                                anchors.horizontalCenter: parent.horizontalCenter
                                spacing: 10
                                Repeater {
                                    model: 6
                                    Rectangle {
                                        id: casilla
                                        required property int index
                                        readonly property bool actual: entradaCodigo.activeFocus
                                            && index === Math.min(entradaCodigo.text.length, 5)
                                        readonly property string digito: entradaCodigo.text.charAt(index)
                                        width: 50; height: 58; radius: 11
                                        color: T.CAMPO
                                        border.width: actual ? 1.5 : 1
                                        border.color: win.error.length > 0 ? T.NEGADO
                                                      : actual ? T.ACENTO
                                                      : digito.length > 0 ? T.TINTA_TENUE : T.BORDE
                                        Behavior on border.color { ColorAnimation { duration: 140 } }

                                        Text {
                                            anchors.centerIn: parent
                                            text: casilla.digito
                                            color: T.TINTA
                                            font.family: fuente
                                            font.pixelSize: 24
                                            font.weight: Font.Bold
                                            scale: text.length > 0 ? 1 : 0.4
                                            Behavior on scale { NumberAnimation { duration: 160; easing.type: Easing.OutBack } }
                                        }
                                        // Cursor parpadeante en la casilla activa vacía.
                                        Rectangle {
                                            anchors.centerIn: parent
                                            width: 2; height: 24
                                            color: T.ACENTO
                                            visible: casilla.actual && casilla.digito.length === 0
                                            SequentialAnimation on opacity {
                                                loops: Animation.Infinite
                                                running: casilla.actual
                                                NumberAnimation { to: 0; duration: 450 }
                                                NumberAnimation { to: 1; duration: 450 }
                                            }
                                        }
                                    }
                                }
                            }

                            MouseArea {
                                anchors.fill: parent
                                cursorShape: Qt.IBeamCursor
                                onClicked: entradaCodigo.forceActiveFocus()
                            }
                        }

                        AvisoError { width: parent.width; mensaje: win.pideCodigo ? win.error : "" }

                        Boton {
                            width: parent.width
                            texto: "Verificar"
                            ocupado: win.ocupado
                            onPulsado: win.verificar()
                        }
                    }

                    // ---------- paso 3: contraseña nueva (tras una temporal) ----------
                    Column {
                        id: pasoNueva
                        width: parent.width
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: 14
                        x: win.pideNueva ? 0 : 60
                        opacity: win.pideNueva ? 1 : 0
                        visible: opacity > 0
                        enabled: win.pideNueva
                        Behavior on x { NumberAnimation { duration: 340; easing.type: Easing.OutCubic } }
                        Behavior on opacity { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }

                        Item {
                            width: filaVolverN.implicitWidth
                            height: filaVolverN.implicitHeight
                            Row {
                                id: filaVolverN
                                spacing: 6
                                opacity: zonaVolverN.containsMouse ? 1 : 0.75
                                Text { text: "\uE72B"; font.family: iconos; font.pixelSize: 12; color: T.ACENTO; anchors.verticalCenter: parent.verticalCenter }
                                Text { text: "Volver"; color: T.ACENTO; font.family: fuente; font.pixelSize: 13; font.weight: Font.DemiBold }
                            }
                            MouseArea {
                                id: zonaVolverN
                                anchors.fill: parent
                                anchors.margins: -6
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: win.volver()
                            }
                        }

                        Column {
                            width: parent.width
                            spacing: 6
                            Text { text: "Crea tu contraseña"; color: T.TINTA; font.family: fuente; font.pixelSize: 24; font.weight: Font.Bold }
                            Text {
                                width: parent.width
                                wrapMode: Text.WordWrap
                                text: "Entraste con una contraseña temporal. Elige una nueva para continuar; solo tú la conocerás."
                                color: T.TINTA_MEDIA
                                font.family: fuente
                                font.pixelSize: 14
                            }
                        }

                        Campo {
                            id: nueva1
                            width: parent.width
                            rotulo: "Contraseña nueva"
                            marcador: "Mínimo 8, con letras y números"
                            icono: "\uE72E"
                            esPassword: true
                            conError: win.error.length > 0 && win.pideNueva
                            onAceptado: nueva2.enfocar()
                            onTeclaSoltada: win.mayus = puente.mayusculas()
                        }
                        Campo {
                            id: nueva2
                            width: parent.width
                            rotulo: "Repítela"
                            icono: "\uE72E"
                            esPassword: true
                            conError: win.error.length > 0 && win.pideNueva
                            onAceptado: win.cambiarContrasena()
                            onTeclaSoltada: win.mayus = puente.mayusculas()
                        }

                        AvisoError { width: parent.width; mensaje: win.pideNueva ? win.error : "" }

                        Boton {
                            width: parent.width
                            texto: "Guardar y entrar"
                            ocupado: win.ocupado
                            onPulsado: win.cambiarContrasena()
                        }
                    }
                }
            }
        }
    }
}
