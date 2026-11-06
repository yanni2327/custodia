// Cuentas y grupos: las cuentas locales de Windows que usan Custodia.
// A la izquierda, las cuentas; a la derecha, el alta de una cuenta y los
// grupos. Las acciones de cada cuenta están en su menú (⋯).
import QtQuick

Item {
    id: hoja

    property var c
    readonly property string titulo: "Cuentas y grupos"
    readonly property string subtitulo: "Son cuentas locales de Windows. Las contraseñas las valida y las guarda Windows, no Custodia."
    readonly property int anchoPreferido: 1120
    readonly property int altoPreferido: 0

    property string filtro: ""
    readonly property var visibles: c
        ? c.cuentas.filter(x => x.usuario.toLowerCase().indexOf(filtro.trim().toLowerCase()) >= 0)
        : []
    property string cuentaMenu: ""

    // =============== cuentas ===============
    Item {
        id: izquierda
        anchors.left: parent.left
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        anchors.right: derecha.left
        anchors.rightMargin: 28

        Item {
            id: cabCuentas
            width: parent.width
            height: 40
            Row {
                anchors.verticalCenter: parent.verticalCenter
                spacing: 8
                Text { text: "Cuentas"; color: T.TINTA; font.family: fuente; font.pixelSize: 16; font.weight: Font.Bold }
                Rectangle {
                    anchors.verticalCenter: parent.verticalCenter
                    width: num.implicitWidth + 14; height: 22; radius: 11
                    color: T.ELEVADO
                    Text { id: num; anchors.centerIn: parent; text: hoja.c ? hoja.c.cuentas.length : 0; color: T.TINTA_MEDIA; font.family: fuente; font.pixelSize: 12; font.weight: Font.DemiBold }
                }
            }
            Rectangle {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                width: 220; height: 38; radius: 19
                color: T.CAMPO
                border.color: buscaCuenta.activeFocus ? T.ACENTO : T.BORDE
                Text { id: lupa; x: 13; anchors.verticalCenter: parent.verticalCenter; text: ""; font.family: iconos; font.pixelSize: 12; color: T.TINTA_TENUE }
                TextInput {
                    id: buscaCuenta
                    anchors.left: lupa.right
                    anchors.leftMargin: 9
                    anchors.right: parent.right
                    anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    clip: true
                    color: T.TINTA
                    font.family: fuente
                    font.pixelSize: 13
                    selectByMouse: true
                    onTextChanged: hoja.filtro = text
                    Text { anchors.verticalCenter: parent.verticalCenter; visible: buscaCuenta.text.length === 0; text: "Buscar una cuenta"; color: T.TINTA_TENUE; font: buscaCuenta.font }
                }
            }
        }

        ListView {
            id: listaCuentas
            anchors.top: cabCuentas.bottom
            anchors.topMargin: 12
            anchors.left: parent.left
            anchors.right: parent.right
            anchors.bottom: parent.bottom
            clip: true
            spacing: 4
            boundsBehavior: Flickable.StopAtBounds
            model: hoja.visibles

            delegate: Rectangle {
                id: cuenta
                required property var modelData
                required property int index
                width: ListView.view.width
                height: 72
                radius: 14
                color: zonaCuenta.containsMouse ? T.ELEVADO : "transparent"
                border.color: T.BORDE_SUAVE
                Behavior on color { ColorAnimation { duration: 120 } }

                MouseArea { id: zonaCuenta; anchors.fill: parent; hoverEnabled: true }

                Image {
                    id: avatar
                    x: 16
                    anchors.verticalCenter: parent.verticalCenter
                    source: "image://iconos/avatar/" + cuenta.modelData.usuario + "?v=" + puente.versionIconos
                    sourceSize: Qt.size(84, 84)
                    width: 42; height: 42
                }
                Column {
                    anchors.left: avatar.right
                    anchors.leftMargin: 14
                    anchors.right: masCuenta.left
                    anchors.rightMargin: 12
                    anchors.verticalCenter: parent.verticalCenter
                    spacing: 5
                    Row {
                        spacing: 8
                        Text {
                            anchors.verticalCenter: parent.verticalCenter
                            text: cuenta.modelData.usuario
                            color: T.TINTA
                            font.family: fuente
                            font.pixelSize: 15
                            font.weight: Font.DemiBold
                        }
                        Rectangle {
                            visible: cuenta.modelData.admin
                            anchors.verticalCenter: parent.verticalCenter
                            width: tAdmin.implicitWidth + 16; height: 22; radius: 11
                            color: Qt.alpha(T.ACENTO, oscuro ? 0.18 : 0.10)
                            Text { id: tAdmin; anchors.centerIn: parent; text: "Administrador"; color: T.ACENTO; font.family: fuente; font.pixelSize: 11; font.weight: Font.DemiBold }
                        }
                        Rectangle {
                            visible: cuenta.modelData.yo
                            anchors.verticalCenter: parent.verticalCenter
                            width: tYo.implicitWidth + 16; height: 22; radius: 11
                            color: T.ELEVADO
                            border.color: T.BORDE
                            Text { id: tYo; anchors.centerIn: parent; text: "Tu cuenta"; color: T.TINTA_MEDIA; font.family: fuente; font.pixelSize: 11; font.weight: Font.DemiBold }
                        }
                        Rectangle {
                            visible: !cuenta.modelData.creada
                            anchors.verticalCenter: parent.verticalCenter
                            width: tWin.implicitWidth + 16; height: 22; radius: 11
                            color: T.ELEVADO
                            border.color: T.BORDE
                            Text { id: tWin; anchors.centerIn: parent; text: "Cuenta de Windows"; color: T.TINTA_MEDIA; font.family: fuente; font.pixelSize: 11; font.weight: Font.DemiBold }
                        }
                        Rectangle {
                            visible: cuenta.modelData.dosPasos
                            anchors.verticalCenter: parent.verticalCenter
                            width: filaDos.implicitWidth + 16; height: 22; radius: 11
                            color: Qt.alpha(T.VERDE, 0.14)
                            Row {
                                id: filaDos
                                anchors.centerIn: parent
                                spacing: 4
                                Text { anchors.verticalCenter: parent.verticalCenter; text: ""; font.family: iconos; font.pixelSize: 10; color: T.VERDE }
                                Text { anchors.verticalCenter: parent.verticalCenter; text: "Verificación activa"; color: T.VERDE; font.family: fuente; font.pixelSize: 11; font.weight: Font.DemiBold }
                            }
                        }
                    }
                    Text {
                        width: parent.width
                        elide: Text.ElideRight
                        text: cuenta.modelData.grupos.length
                              ? cuenta.modelData.grupos.join(", ")
                              : "Sin grupos"
                        color: T.TINTA_MEDIA
                        font.family: fuente
                        font.pixelSize: 12
                    }
                }
                IconoBoton {
                    id: masCuenta
                    anchors.right: parent.right
                    anchors.rightMargin: 14
                    anchors.verticalCenter: parent.verticalCenter
                    glifo: ""
                    pista: "Acciones"
                    onPulsado: {
                        hoja.cuentaMenu = cuenta.modelData.usuario
                        const p = masCuenta.mapToItem(hoja, masCuenta.width - menu.anchoMenu, masCuenta.height + 4)
                        menu.abrir(p.x, p.y, [
                            { cabecera: true, texto: cuenta.modelData.sid },
                            { separador: true },
                            { texto: "Asignar a un grupo…", glifo: "", accion: "asignar" },
                            {
                                texto: "Quitar de un grupo…", glifo: "", accion: "quitarGrupo",
                                desactivada: cuenta.modelData.grupos.filter(
                                    g => g.toLowerCase() !== hoja.c.grupoApp.toLowerCase()).length === 0
                            },
                            {
                                texto: cuenta.modelData.yo ? "Tu contraseña se cambia en tu perfil"
                                                           : "Restablecer contraseña…",
                                glifo: "", accion: "contrasena",
                                desactivada: cuenta.modelData.yo
                            },
                            {
                                texto: cuenta.modelData.yo ? "Tu verificación se cambia en tu perfil"
                                     : cuenta.modelData.dosPasos ? "Restablecer verificación en dos pasos…"
                                     : "Sin verificación en dos pasos",
                                glifo: "", accion: "restablecer",
                                desactivada: cuenta.modelData.yo || !cuenta.modelData.dosPasos
                            },
                            { separador: true },
                            // Las cuentas que ya existían en Windows no se borran:
                            // se retiran de Custodia y siguen intactas en el equipo.
                            cuenta.modelData.creada
                                ? { texto: "Eliminar la cuenta", glifo: "", accion: "eliminar", peligro: true }
                                : { texto: "Retirar de Custodia", glifo: "", accion: "retirar", peligro: true }
                        ])
                    }
                }
            }
        }

        Text {
            visible: hoja.visibles.length === 0
            anchors.centerIn: listaCuentas
            text: hoja.filtro ? "Ninguna cuenta se llama así." : "Todavía no hay cuentas."
            color: T.TINTA_MEDIA
            font.family: fuente
            font.pixelSize: 14
        }
    }

    // =============== cuenta nueva + grupos ===============
    Flickable {
        id: derecha
        width: 340
        anchors.right: parent.right
        anchors.top: parent.top
        anchors.bottom: parent.bottom
        clip: true
        contentHeight: columnaDer.implicitHeight
        boundsBehavior: Flickable.StopAtBounds

        Column {
            id: columnaDer
            width: derecha.width
            spacing: 22

            // ---- alta de cuenta ----
            Rectangle {
                width: parent.width
                height: formulario.implicitHeight + 44
                radius: 16
                color: oscuro ? T.FONDO : T.ELEVADO
                Behavior on color { ColorAnimation { duration: 260 } }

                Column {
                    id: formulario
                    x: 22
                    y: 22
                    width: parent.width - 44
                    spacing: 14

                    Text { text: "Cuenta nueva"; color: T.TINTA; font.family: fuente; font.pixelSize: 16; font.weight: Font.Bold }
                    Campo {
                        id: nuevoUsuario
                        width: parent.width
                        rotulo: "Usuario"
                        marcador: "Hasta 20 caracteres"
                        icono: ""
                        onAceptado: nuevaClave.enfocar()
                    }
                    Campo {
                        id: nuevaClave
                        width: parent.width
                        rotulo: "Contraseña"
                        marcador: "Debe cumplir la política del equipo"
                        icono: ""
                        esPassword: true
                        onAceptado: botonCrear.pulsado()
                    }
                    Interruptor {
                        id: nuevoAdmin
                        width: parent.width
                        texto: "Puede administrar Custodia"
                        detalle: "Gestiona cuentas y consulta la bitácora."
                    }
                    Boton {
                        id: botonCrear
                        width: parent.width
                        glifo: ""
                        texto: "Crear la cuenta"
                        onPulsado: hoja.c.crear(nuevoUsuario.text, nuevaClave.text, nuevoAdmin.marcado)
                    }
                    Connections {
                        target: hoja.c
                        ignoreUnknownSignals: true
                        function onCuentaCreada() {
                            nuevoUsuario.text = ""
                            nuevaClave.text = ""
                            nuevoAdmin.marcado = false
                        }
                    }
                }
            }

            // ---- cuenta que ya existe en Windows ----
            Boton {
                width: parent.width
                primario: false
                glifo: ""
                texto: "Añadir una cuenta de Windows existente"
                onPulsado: hoja.c.incorporar()
            }

            // ---- grupos ----
            Column {
                width: parent.width
                spacing: 8

                Item {
                    width: parent.width
                    height: 34
                    Text { anchors.verticalCenter: parent.verticalCenter; text: "Grupos"; color: T.TINTA; font.family: fuente; font.pixelSize: 16; font.weight: Font.Bold }
                    Rectangle {
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        width: filaNuevoGrupo.implicitWidth + 20; height: 32; radius: 9
                        color: zonaNuevoGrupo.containsMouse ? Qt.alpha(T.ACENTO, 0.12) : "transparent"
                        Row {
                            id: filaNuevoGrupo
                            anchors.centerIn: parent
                            spacing: 6
                            Text { anchors.verticalCenter: parent.verticalCenter; text: ""; font.family: iconos; font.pixelSize: 11; color: T.ACENTO }
                            Text { anchors.verticalCenter: parent.verticalCenter; text: "Nuevo grupo"; color: T.ACENTO; font.family: fuente; font.pixelSize: 13; font.weight: Font.DemiBold }
                        }
                        MouseArea { id: zonaNuevoGrupo; anchors.fill: parent; hoverEnabled: true; cursorShape: Qt.PointingHandCursor; onClicked: hoja.c.crearGrupo() }
                    }
                }

                Repeater {
                    model: hoja.c ? hoja.c.grupos : []
                    Rectangle {
                        id: grupo
                        required property var modelData
                        width: parent.width
                        height: 54
                        radius: 12
                        color: zonaGrupo.containsMouse ? T.ELEVADO : "transparent"
                        border.color: T.BORDE_SUAVE
                        Behavior on color { ColorAnimation { duration: 120 } }
                        MouseArea { id: zonaGrupo; anchors.fill: parent; hoverEnabled: true }
                        Rectangle {
                            id: icoGrupo
                            x: 12
                            anchors.verticalCenter: parent.verticalCenter
                            width: 32; height: 32; radius: 10
                            color: Qt.alpha(T.ACENTO, 0.12)
                            Text { anchors.centerIn: parent; text: ""; font.family: iconos; font.pixelSize: 14; color: T.ACENTO }
                        }
                        // Los internos no se pueden eliminar: se dice en vez de
                        // esconder el botón sin explicación.
                        Rectangle {
                            id: marcaInterno
                            visible: grupo.modelData.interno
                            anchors.right: parent.right
                            anchors.rightMargin: 12
                            anchors.verticalCenter: parent.verticalCenter
                            width: tInterno.implicitWidth + 14; height: 20; radius: 10
                            color: T.ELEVADO
                            border.color: T.BORDE
                            Text { id: tInterno; anchors.centerIn: parent; text: "Interno"; color: T.TINTA_MEDIA; font.family: fuente; font.pixelSize: 11; font.weight: Font.DemiBold }
                        }
                        IconoBoton {
                            id: borrarGrupo
                            visible: !grupo.modelData.interno
                            anchors.right: parent.right
                            anchors.rightMargin: 8
                            anchors.verticalCenter: parent.verticalCenter
                            lado: 34
                            opacity: zonaGrupo.containsMouse ? 1 : 0.45
                            glifo: ""
                            tamGlifo: 14
                            peligro: true
                            pista: "Eliminar el grupo"
                            pistaArriba: true
                            onPulsado: hoja.c.eliminarGrupo(grupo.modelData.nombre)
                        }
                        Column {
                            anchors.left: icoGrupo.right
                            anchors.leftMargin: 12
                            anchors.right: grupo.modelData.interno ? marcaInterno.left : borrarGrupo.left
                            anchors.rightMargin: 8
                            anchors.verticalCenter: parent.verticalCenter
                            spacing: 2
                            Text { width: parent.width; elide: Text.ElideRight; text: grupo.modelData.nombre; color: T.TINTA; font.family: fuente; font.pixelSize: 13; font.weight: Font.DemiBold }
                            Text {
                                width: parent.width
                                elide: Text.ElideRight
                                text: (grupo.modelData.miembros === 1 ? "1 miembro" : grupo.modelData.miembros + " miembros")
                                      + (grupo.modelData.descripcion ? ", " + grupo.modelData.descripcion : "")
                                color: T.TINTA_MEDIA
                                font.family: fuente
                                font.pixelSize: 12
                            }
                        }
                    }
                }
            }
        }
    }

    MenuFlotante {
        id: menu
        anchoMenu: 320
        onElegido: (accion) => {
            if (accion === "asignar") hoja.c.asignar(hoja.cuentaMenu)
            else if (accion === "restablecer") hoja.c.restablecerDosPasos(hoja.cuentaMenu)
            else if (accion === "quitarGrupo") hoja.c.quitarDeGrupo(hoja.cuentaMenu)
            else if (accion === "retirar") hoja.c.retirar(hoja.cuentaMenu)
            else if (accion === "contrasena") hoja.c.restablecerContrasena(hoja.cuentaMenu)
            else if (accion === "eliminar") hoja.c.eliminar(hoja.cuentaMenu)
        }
    }
}
