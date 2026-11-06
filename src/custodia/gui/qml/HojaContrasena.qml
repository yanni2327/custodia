// Cambiar la propia contraseña. Pide la actual: así una sesión abierta y
// desatendida no basta para quedarse con la cuenta.
import QtQuick

Item {
    id: hoja

    property var c
    readonly property string titulo: "Cambiar mi contraseña"
    readonly property string subtitulo: ""
    readonly property int anchoPreferido: 520
    readonly property int altoPreferido: columna.implicitHeight
    property string error: ""

    Timer { interval: 80; running: true; onTriggered: actual.enfocar() }

    function guardar() {
        error = hoja.c.cambiar(actual.text, nueva1.text, nueva2.text)
        if (error) {
            if (error.indexOf("actual") >= 0) { actual.text = ""; actual.enfocar() }
            else { nueva2.text = ""; nueva1.enfocar() }
        }
    }

    Column {
        id: columna
        width: parent.width
        spacing: 0

        Text {
            width: parent.width
            wrapMode: Text.WordWrap
            lineHeight: 1.25
            text: "Es la contraseña de tu cuenta de Windows: cambiará también para entrar al equipo."
            color: T.TINTA_MEDIA
            font.family: fuente
            font.pixelSize: 13
        }
        Item { width: 1; height: 20 }
        Campo {
            id: actual
            width: parent.width
            rotulo: "Contraseña actual"
            icono: ""
            esPassword: true
            conError: hoja.error.indexOf("actual") >= 0
            onAceptado: nueva1.enfocar()
            onTeclaSoltada: hoja.error = ""
        }
        Item { width: 1; height: 14 }
        Campo {
            id: nueva1
            width: parent.width
            rotulo: "Contraseña nueva"
            marcador: "Al menos 8 caracteres, con letras y números"
            icono: ""
            esPassword: true
            conError: hoja.error.length > 0 && hoja.error.indexOf("actual") < 0
            onAceptado: nueva2.enfocar()
            onTeclaSoltada: hoja.error = ""
        }
        Item { width: 1; height: 14 }
        Campo {
            id: nueva2
            width: parent.width
            rotulo: "Repite la nueva"
            icono: ""
            esPassword: true
            conError: hoja.error.length > 0 && hoja.error.indexOf("actual") < 0
            onAceptado: hoja.guardar()
            onTeclaSoltada: hoja.error = ""
        }
        Item { width: 1; height: 12; visible: hoja.error.length > 0 }
        AvisoError { width: parent.width; mensaje: hoja.error }

        Item { width: 1; height: 26 }
        Item {
            width: parent.width
            height: 44
            Row {
                anchors.right: parent.right
                spacing: 10
                Boton { primario: false; texto: "Cancelar"; onPulsado: puente.cerrarHoja() }
                Boton { texto: "Cambiar contraseña"; onPulsado: hoja.guardar() }
            }
        }
    }
}
