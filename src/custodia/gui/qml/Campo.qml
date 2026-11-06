// Campo de texto con rótulo, icono, halo de foco animado y, para contraseñas,
// botón de mostrar/ocultar. Lo usan las pantallas QML de Custodia.
import QtQuick

Item {
    id: raiz

    property alias text: entrada.text
    property alias entrada: entrada
    property string rotulo: ""
    property string marcador: ""
    property string icono: ""
    property bool esPassword: false
    property bool mostrar: false
    property bool conError: false

    signal aceptado()
    signal teclaSoltada()
    signal focoCambiado()

    function enfocar() { entrada.forceActiveFocus() }

    implicitHeight: columna.implicitHeight

    readonly property color colorBorde: conError ? T.NEGADO
                                      : entrada.activeFocus ? T.ACENTO
                                      : hover.hovered ? T.TINTA_TENUE : T.BORDE

    Column {
        id: columna
        width: parent.width
        spacing: 7

        Text {
            text: raiz.rotulo
            color: T.TINTA_MEDIA
            font.family: fuente
            font.pixelSize: 12
            font.weight: Font.DemiBold
        }

        Rectangle {
            id: caja
            width: parent.width
            height: 48
            radius: 10
            color: T.CAMPO
            border.width: entrada.activeFocus ? 1.5 : 1
            border.color: raiz.colorBorde
            Behavior on border.color { ColorAnimation { duration: 160 } }

            // Halo exterior: aparece suave al enfocar.
            Rectangle {
                anchors.fill: parent
                anchors.margins: -4
                radius: 14
                color: "transparent"
                border.width: 4
                border.color: Qt.alpha(raiz.conError ? T.NEGADO : T.ACENTO,
                                       entrada.activeFocus ? 0.22 : 0)
                Behavior on border.color { ColorAnimation { duration: 180 } }
            }

            HoverHandler { id: hover; cursorShape: Qt.IBeamCursor }
            TapHandler { onTapped: entrada.forceActiveFocus() }

            Text {
                id: ico
                text: raiz.icono
                font.family: iconos
                font.pixelSize: 16
                color: entrada.activeFocus ? T.ACENTO : T.TINTA_TENUE
                Behavior on color { ColorAnimation { duration: 160 } }
                anchors.left: parent.left
                anchors.leftMargin: 15
                anchors.verticalCenter: parent.verticalCenter
            }

            TextInput {
                id: entrada
                anchors.left: ico.right
                anchors.leftMargin: 12
                anchors.right: ojo.visible ? ojo.left : parent.right
                anchors.rightMargin: 12
                anchors.verticalCenter: parent.verticalCenter
                color: T.TINTA
                font.family: fuente
                font.pixelSize: 14
                selectionColor: T.ACENTO
                selectedTextColor: "white"
                selectByMouse: true
                clip: true
                echoMode: raiz.esPassword && !raiz.mostrar ? TextInput.Password
                                                           : TextInput.Normal
                passwordCharacter: "•"
                inputMethodHints: raiz.esPassword
                    ? (Qt.ImhSensitiveData | Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase)
                    : (Qt.ImhNoPredictiveText | Qt.ImhNoAutoUppercase)
                onAccepted: raiz.aceptado()
                Keys.onReleased: raiz.teclaSoltada()
                onActiveFocusChanged: raiz.focoCambiado()

                Text {
                    anchors.verticalCenter: parent.verticalCenter
                    text: raiz.marcador
                    color: T.TINTA_TENUE
                    font: entrada.font
                    visible: entrada.text.length === 0 && entrada.preeditText.length === 0
                }
            }

            // Mostrar / ocultar contraseña.
            Text {
                id: ojo
                visible: raiz.esPassword
                text: raiz.mostrar ? "" : ""
                font.family: iconos
                font.pixelSize: 16
                color: zonaOjo.containsMouse ? T.TINTA : T.TINTA_TENUE
                anchors.right: parent.right
                anchors.rightMargin: 15
                anchors.verticalCenter: parent.verticalCenter

                MouseArea {
                    id: zonaOjo
                    anchors.fill: parent
                    anchors.margins: -8
                    hoverEnabled: true
                    cursorShape: Qt.PointingHandCursor
                    onClicked: {
                        raiz.mostrar = !raiz.mostrar
                        entrada.forceActiveFocus()
                    }
                }
            }
        }
    }
}
