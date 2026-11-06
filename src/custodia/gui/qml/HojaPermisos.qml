// Permisos de un elemento: la lista de control de acceso tal como la tiene
// Windows, y un formulario para conceder un permiso nuevo. Las entradas
// heredadas se muestran atenuadas y no se pueden quitar desde aquí.
import QtQuick

Item {
    id: hoja

    property var c
    readonly property string titulo: c ? "Permisos de «" + c.nombre + "»" : "Permisos"
    readonly property string subtitulo: "Cada cambio lo autoriza Windows: hace falta ser administrador o dueño del elemento."
    readonly property int anchoPreferido: 1000
    readonly property int altoPreferido: 0

    property var marcados: [false, false, false, false, false]
    readonly property var sugerencias: {
        if (!c) return []
        const t = quien.text.trim().toLowerCase()
        if (!t) return c.principales.slice(0, 6)
        return c.principales.filter(p => p.toLowerCase().indexOf(t) >= 0 && p.toLowerCase() !== t).slice(0, 6)
    }

    function alternar(i) {
        const m = marcados.slice()
        m[i] = !m[i]
        // «Control total» incluye a los demás: marcarlo los marca todos.
        if (i === 4 && m[4]) for (let k = 0; k < 4; k++) m[k] = true
        if (i < 4 && !m[i]) m[4] = false
        marcados = m
    }

    Connections {
        target: hoja.c
        ignoreUnknownSignals: true
        function onConcedido() {
            quien.text = ""
            hoja.marcados = [false, false, false, false, false]
        }
    }

    // =============== entradas ===============
    Item {
        id: izquierda
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.right: derecha.left
        anchors.rightMargin: 28

        Item {
            id: cabEntradas
            width: parent.width
            height: 30
            Text { anchors.verticalCenter: parent.verticalCenter; text: "Quién tiene acceso"; color: T.TINTA; font.family: fuente; font.pixelSize: 16; font.weight: Font.Bold }
            Text {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                width: parent.width * 0.55
                horizontalAlignment: Text.AlignRight
                elide: Text.ElideMiddle
                text: hoja.c ? hoja.c.rutaCompleta : ""
                color: T.TINTA_TENUE
                font.family: "Consolas"
                font.pixelSize: 12
            }
        }

        ListView {
            id: lista
            anchors.top: cabEntradas.bottom
            anchors.topMargin: 12
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: nota.top
            anchors.bottomMargin: 12
            clip: true
            spacing: 6
            boundsBehavior: Flickable.StopAtBounds
            model: hoja.c ? hoja.c.entradas : []

            delegate: Rectangle {
                id: entrada
                required property var modelData
                required property int index
                width: ListView.view.width
                height: 76
                radius: 14
                color: zonaEntrada.containsMouse && !modelData.heredado ? T.ELEVADO : "transparent"
                border.color: T.BORDE_SUAVE
                opacity: modelData.heredado ? 0.62 : 1
                Behavior on color { ColorAnimation { duration: 120 } }

                MouseArea { id: zonaEntrada; anchors.fill: parent; hoverEnabled: true }

                Image {
                    id: avatar
                    x: 16
                    anchors.verticalCenter: parent.verticalCenter
                    source: "image://iconos/avatar/" + entrada.modelData.corto + "?v=" + puente.versionIconos
                    sourceSize: Qt.size(76, 76)
                    width: 38; height: 38
                }
                Column {
                    anchors.left: avatar.right
                    anchors.leftMargin: 14
                    anchors.right: quitar.left
                    anchors.rightMargin: 10
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 7
                    Row {
                        spacing: 8
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: entrada.modelData.corto
                            color: T.TINTA
                            font.family: fuente
                            font.pixelSize: 14
                            font.weight: Font.DemiBold
                        }
                        Rectangle {
                            visible: !entrada.modelData.permitir
                            anchors.verticalCenter: parent.verticalCenter
                            width: tDen.implicitWidth + 14; height: 20; radius: 10
                            color: Qt.alpha(T.NEGADO, 0.15)
                            Text { id: tDen; anchors.centerIn: parent; text: "Denegado"; color: T.NEGADO; font.family: fuente; font.pixelSize: 11; font.weight: Font.DemiBold }
                        }
                        Rectangle {
                            visible: entrada.modelData.heredado
                            anchors.verticalCenter: parent.verticalCenter
                            width: tHer.implicitWidth + 14; height: 20; radius: 10
                            color: T.ELEVADO
                            border.color: T.BORDE
                            Text { id: tHer; anchors.centerIn: parent; text: "Heredado"; color: T.TINTA_MEDIA; font.family: fuente; font.pixelSize: 11; font.weight: Font.DemiBold }
                        }
                    }
                    Row {
                        spacing: 5
                        Repeater {
                            model: entrada.modelData.permisos.length ? entrada.modelData.permisos : ["Sin permisos"]
                            Rectangle {
                                id: chip
                                required property string modelData
                                height: 22
                                width: tChip.implicitWidth + 16
                                radius: 11
                                color: entrada.modelData.permitir ? Qt.alpha(T.ACENTO, oscuro ? 0.16 : 0.09) : Qt.alpha(T.NEGADO, 0.10)
                                Text {
                                    id: tChip
                                    anchors.centerIn: parent
                                    text: chip.modelData
                                    color: entrada.modelData.permitir ? T.TINTA : T.NEGADO
                                    font.family: fuente
                                    font.pixelSize: 11
                                    font.weight: Font.Medium
                                }
                            }
                        }
                        Text {
                            visible: entrada.modelData.propagado
                            anchors.verticalCenter: parent.verticalCenter
                            leftPadding: 4
                            text: "y lo que contiene"
                            color: T.TINTA_TENUE
                            font.family: fuente
                            font.pixelSize: 11
                        }
                    }
                }
                IconoBoton {
                    id: quitar
                    anchors.right: parent.right
                    anchors.rightMargin: 14
                    anchors.verticalCenter: parent.verticalCenter
                    visible: !entrada.modelData.heredado
                    opacity: zonaEntrada.containsMouse ? 1 : 0.5
                    glifo: ""
                    peligro: true
                    pista: "Quitar esta entrada"
                    onPulsado: hoja.c.quitar(entrada.index)
                }
            }
        }

        Text {
            id: nota
            anchors.bottom: parent.bottom
            width: parent.width
            wrapMode: Text.WordWrap
            text: "Las entradas heredadas vienen de la carpeta que contiene este elemento; se cambian allí."
            color: T.TINTA_TENUE
            font.family: fuente
            font.pixelSize: 12
        }
    }

    // =============== conceder ===============
    Rectangle {
        id: derecha
        width: 340
        anchors.right: parent.right
        anchors.top: parent.top
        height: Math.min(parent.height, formulario.implicitHeight + 44)
        radius: 16
        color: oscuro ? T.FONDO : T.ELEVADO
        Behavior on color { ColorAnimation { duration: 260 } }

        Column {
            id: formulario
            x: 22
            y: 22
            width: parent.width - 44
            spacing: 14

            Text { text: "Conceder un permiso"; color: T.TINTA; font.family: fuente; font.pixelSize: 16; font.weight: Font.Bold }

            Column {
                width: parent.width
                spacing: 6
                z: 10
                Campo {
                    id: quien
                    width: parent.width
                    rotulo: "A quién"
                    marcador: "Cuenta o grupo"
                    icono: ""
                }
                // Sugerencias mientras se escribe.
                Rectangle {
                    width: parent.width
                    visible: quien.entrada.activeFocus && hoja.sugerencias.length > 0
                    height: columnaSug.implicitHeight + 8
                    radius: 10
                    color: T.PANEL
                    border.color: T.BORDE
                    Column {
                        id: columnaSug
                        x: 4; y: 4
                        width: parent.width - 8
                        Repeater {
                            model: hoja.sugerencias
                            Rectangle {
                                id: sug
                                required property string modelData
                                width: columnaSug.width
                                height: 34
                                radius: 7
                                color: zonaSug.containsMouse ? Qt.alpha(T.ACENTO, 0.12) : "transparent"
                                Text {
                                    x: 10
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: sug.modelData
                                    color: T.TINTA
                                    font.family: fuente
                                    font.pixelSize: 13
                                }
                                MouseArea {
                                    id: zonaSug
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onPressed: { quien.text = sug.modelData; quien.entrada.focus = false }
                                }
                            }
                        }
                    }
                }
            }

            Column {
                width: parent.width
                spacing: 8
                Text { text: "Qué puede hacer"; color: T.TINTA_MEDIA; font.family: fuente; font.pixelSize: 12; font.weight: Font.DemiBold }
                Flow {
                    width: parent.width
                    spacing: 6
                    Repeater {
                        model: hoja.c ? hoja.c.ofrecidos : []
                        Rectangle {
                            id: op
                            required property string modelData
                            required property int index
                            readonly property bool si: hoja.marcados[index]
                            height: 34
                            width: tOp.implicitWidth + 40
                            radius: 17
                            color: si ? T.ACENTO : (zonaOp.containsMouse ? T.ELEVADO : "transparent")
                            border.width: si ? 0 : 1
                            border.color: T.BORDE
                            Behavior on color { ColorAnimation { duration: 140 } }
                            Row {
                                anchors.centerIn: parent
                                spacing: 6
                                Text {
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: op.si ? "" : ""
                                    font.family: iconos
                                    font.pixelSize: 10
                                    color: op.si ? "white" : T.TINTA_MEDIA
                                }
                                Text {
                                    id: tOp
                                    anchors.verticalCenter: parent.verticalCenter
                                    text: op.modelData
                                    color: op.si ? "white" : T.TINTA
                                    font.family: fuente
                                    font.pixelSize: 13
                                    font.weight: Font.Medium
                                }
                            }
                            MouseArea {
                                id: zonaOp
                                anchors.fill: parent
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onClicked: hoja.alternar(op.index)
                            }
                        }
                    }
                }
            }

            Interruptor {
                id: hereda
                width: parent.width
                marcado: true
                texto: "Aplicar también a lo que contenga"
                detalle: "Las carpetas y archivos de dentro lo heredan."
            }

            Boton {
                width: parent.width
                glifo: ""
                texto: "Conceder"
                onPulsado: hoja.c.conceder(quien.text, hoja.marcados, hereda.marcado)
            }
        }
    }
}
