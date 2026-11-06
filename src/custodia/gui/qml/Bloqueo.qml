// Pantalla de bloqueo: tapa la ventana entera con el azul de la bóveda (el
// mismo del inicio de sesión), muestra la hora y pide la contraseña.
//
// Es opaca a propósito: en cuanto se bloquea, lo que había en pantalla deja
// de verse. La comprobación la hace Python (`puente.desbloquear`), con las
// mismas reglas que el inicio de sesión.
import QtQuick
import QtQuick.Effects

Item {
    id: bloqueo
    anchors.fill: parent
    z: 2000

    readonly property bool activo: !!puente.bloqueo.activo
    property bool pideCodigo: false
    property bool ocupado: false
    property string error: ""
    property real sacudida: 0
    property date ahora: new Date()

    visible: activo || opacity > 0.01
    opacity: activo ? 1 : 0
    Behavior on opacity { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }

    onActivoChanged: {
        if (activo) {
            pideCodigo = false
            error = ""
            campoPassword.text = ""
            campoCodigo.text = ""
            entrada.restart()
            enfocar.restart()
        } else {
            campoPassword.text = ""
            campoCodigo.text = ""
        }
    }

    function desbloquear() {
        if (ocupado) return
        if (campoPassword.text.length === 0) {
            mostrarError("Escribe tu contraseña.")
            campoPassword.enfocar()
            return
        }
        if (pideCodigo && campoCodigo.text.trim().length === 0) {
            mostrarError("Escribe el código de tu app de autenticación.")
            campoCodigo.enfocar()
            return
        }
        error = ""
        puente.desbloquear(campoPassword.text, pideCodigo ? campoCodigo.text.trim() : "")
    }
    function mostrarError(m) {
        error = m
        animSacudida.restart()
    }

    Connections {
        target: puente
        function onDesbloqueoError(m) {
            bloqueo.mostrarError(m)
            if (bloqueo.pideCodigo) { campoCodigo.text = ""; campoCodigo.enfocar() }
            else { campoPassword.text = ""; campoPassword.enfocar() }
        }
        function onDesbloqueoPideCodigo() {
            bloqueo.error = ""
            bloqueo.pideCodigo = true
            campoCodigo.enfocar()
        }
        function onDesbloqueoOcupado(v) { bloqueo.ocupado = v }
    }

    Timer { id: enfocar; interval: 60; onTriggered: campoPassword.enfocar() }
    Timer {
        interval: 1000
        running: bloqueo.activo
        repeat: true
        triggeredOnStart: true
        onTriggered: bloqueo.ahora = new Date()
    }

    SequentialAnimation {
        id: animSacudida
        NumberAnimation { target: bloqueo; property: "sacudida"; to: -10; duration: 45 }
        NumberAnimation { target: bloqueo; property: "sacudida"; to: 9; duration: 70 }
        NumberAnimation { target: bloqueo; property: "sacudida"; to: -6; duration: 65 }
        NumberAnimation { target: bloqueo; property: "sacudida"; to: 3; duration: 60 }
        NumberAnimation { target: bloqueo; property: "sacudida"; to: 0; duration: 55 }
    }
    ParallelAnimation {
        id: entrada
        NumberAnimation { target: tarjeta; property: "scale"; from: 0.94; to: 1; duration: 420; easing.type: Easing.OutBack; easing.overshoot: 1.1 }
        NumberAnimation { target: tarjeta; property: "opacity"; from: 0; to: 1; duration: 320; easing.type: Easing.OutCubic }
    }

    // Nada de lo de detrás recibe ratón ni rueda.
    MouseArea {
        anchors.fill: parent
        hoverEnabled: true
        acceptedButtons: Qt.AllButtons
        onWheel: (ev) => ev.accepted = true
    }

    // ---- fondo de la bóveda ----------------------------------------------------
    Rectangle {
        anchors.fill: parent
        gradient: Gradient {
            GradientStop { position: 0.0; color: Qt.lighter(T.ACENTO, 1.05) }
            GradientStop { position: 0.5; color: T.ACENTO_HONDO }
            GradientStop { position: 1.0; color: "#0A1F45" }
        }
    }
    Repeater {
        model: [
            { x: -0.08, y: -0.12, d: 0.42, dx: 30, dy: 22, t: 9000 },
            { x: 0.70, y: 0.55, d: 0.50, dx: -26, dy: -30, t: 11000 },
            { x: 0.78, y: 0.05, d: 0.18, dx: -18, dy: 24, t: 7000 }
        ]
        Rectangle {
            required property var modelData
            readonly property real bx: modelData.x * bloqueo.width
            readonly property real by: modelData.y * bloqueo.height
            width: modelData.d * bloqueo.width
            height: width
            radius: width / 2
            color: "white"
            opacity: 0.06
            x: bx
            y: by
            SequentialAnimation on x {
                running: bloqueo.activo
                loops: Animation.Infinite
                NumberAnimation { to: bx + modelData.dx; duration: modelData.t; easing.type: Easing.InOutSine }
                NumberAnimation { to: bx; duration: modelData.t; easing.type: Easing.InOutSine }
            }
            SequentialAnimation on y {
                running: bloqueo.activo
                loops: Animation.Infinite
                NumberAnimation { to: by + modelData.dy; duration: modelData.t * 1.3; easing.type: Easing.InOutSine }
                NumberAnimation { to: by; duration: modelData.t * 1.3; easing.type: Easing.InOutSine }
            }
        }
    }

    // Hora y fecha: lo primero que se espera ver en una pantalla de bloqueo.
    Column {
        x: 56
        anchors.bottom: parent.bottom
        anchors.bottomMargin: 48
        spacing: 2
        Text {
            text: Qt.formatTime(bloqueo.ahora, "HH:mm")
            color: "white"
            font.family: fuente
            font.pixelSize: 84
            font.weight: Font.Light
        }
        Text {
            text: {
                const dias = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"]
                const meses = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                               "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
                const d = bloqueo.ahora
                const t = dias[d.getDay()] + ", " + d.getDate() + " de " + meses[d.getMonth()]
                return t.charAt(0).toUpperCase() + t.slice(1)
            }
            color: Qt.alpha("white", 0.75)
            font.family: fuente
            font.pixelSize: 18
        }
    }

    Row {
        x: 56
        y: 44
        spacing: 12
        Rectangle {
            width: 40; height: 40; radius: 11
            color: "white"
            Image { anchors.centerIn: parent; source: logoUrl; width: 26; height: 26; mipmap: true }
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: "Custodia"
            color: "white"
            font.family: fuente
            font.pixelSize: 18
            font.weight: Font.Bold
        }
    }

    // ---- tarjeta ----------------------------------------------------------------
    Rectangle {
        id: tarjeta
        width: 380
        height: columna.implicitHeight + 64
        anchors.centerIn: parent
        anchors.horizontalCenterOffset: bloqueo.width > 1100 ? bloqueo.width * 0.18 : 0
        radius: 22
        color: T.PANEL
        border.color: T.BORDE
        layer.enabled: true
        layer.effect: MultiEffect {
            shadowEnabled: true
            shadowColor: "#000000"
            shadowOpacity: 0.45
            shadowBlur: 1.0
            blurMax: 56
            shadowVerticalOffset: 18
        }
        transform: Translate { x: bloqueo.sacudida }

        Column {
            id: columna
            x: 32
            y: 32
            width: parent.width - 64
            spacing: 0

            Image {
                anchors.horizontalCenter: parent.horizontalCenter
                source: "image://iconos/avatar/" + puente.usuario + "?v=" + puente.versionIconos
                sourceSize: Qt.size(144, 144)
                width: 72; height: 72
            }
            Item { width: 1; height: 14 }
            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                text: puente.usuario
                color: T.TINTA
                font.family: fuente
                font.pixelSize: 22
                font.weight: Font.Bold
            }
            Item { width: 1; height: 4 }
            Text {
                width: parent.width
                horizontalAlignment: Text.AlignHCenter
                wrapMode: Text.WordWrap
                text: puente.bloqueo.motivo || ""
                color: T.TINTA_MEDIA
                font.family: fuente
                font.pixelSize: 13
                lineHeight: 1.25
            }
            Item { width: 1; height: 22 }

            Campo {
                id: campoPassword
                width: parent.width
                rotulo: "Contraseña"
                marcador: "Tu contraseña"
                icono: ""
                esPassword: true
                enabled: !bloqueo.pideCodigo
                opacity: enabled ? 1 : 0.55
                conError: bloqueo.error.length > 0 && !bloqueo.pideCodigo
                onAceptado: bloqueo.desbloquear()
            }
            Item { width: 1; height: 12; visible: campoCodigo.visible }
            Campo {
                id: campoCodigo
                visible: bloqueo.pideCodigo
                width: parent.width
                rotulo: "Código de verificación"
                marcador: "6 dígitos"
                icono: ""
                conError: bloqueo.error.length > 0 && bloqueo.pideCodigo
                onAceptado: bloqueo.desbloquear()
            }
            Item { width: 1; height: 12 }
            AvisoError { width: parent.width; mensaje: bloqueo.error }
            Item { width: 1; height: 8 }
            Boton {
                width: parent.width
                texto: bloqueo.pideCodigo ? "Verificar" : "Desbloquear"
                ocupado: bloqueo.ocupado
                onPulsado: bloqueo.desbloquear()
            }
            Item { width: 1; height: 8 }
            Boton {
                width: parent.width
                primario: false
                texto: "Cerrar sesión"
                onPulsado: puente.cerrarSesionDesdeBloqueo()
            }
        }
    }
}
