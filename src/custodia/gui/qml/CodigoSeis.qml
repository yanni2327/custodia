// Seis casillas para un código de verificación. Se escribe de corrido (un
// solo campo oculto debajo) y se envía solo al completar el sexto dígito.
import QtQuick

Item {
    id: codigo

    property alias text: entrada.text
    property bool conError: false

    signal completado(string valor)

    function enfocar() { entrada.forceActiveFocus() }
    function limpiar() { entrada.text = "" }

    width: 6 * 50 + 5 * 10
    height: 58

    TextInput {
        id: entrada
        width: 1; height: 1
        opacity: 0
        maximumLength: 6
        inputMethodHints: Qt.ImhDigitsOnly
        validator: RegularExpressionValidator { regularExpression: /[0-9]{0,6}/ }
        onTextChanged: {
            if (text.length > 0) codigo.conError = false
            if (text.length === 6) codigo.completado(text)
        }
    }

    Row {
        spacing: 10
        Repeater {
            model: 6
            Rectangle {
                id: casilla
                required property int index
                readonly property bool actual: entrada.activeFocus
                    && index === Math.min(entrada.text.length, 5)
                readonly property string digito: entrada.text.charAt(index)
                width: 50; height: 58; radius: 11
                color: T.CAMPO
                border.width: actual ? 1.5 : 1
                border.color: codigo.conError ? T.NEGADO
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
        onClicked: entrada.forceActiveFocus()
    }
}
