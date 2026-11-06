// Botón de filtro con un rótulo y el valor elegido. Al pulsarlo, quien lo usa
// abre un MenuFlotante con las opciones (ver HojaBitacora.qml).
import QtQuick

Rectangle {
    id: desplegable

    property string rotulo: ""
    property string valor: ""
    property bool activo: false      // hay un filtro distinto de "todos"

    signal pulsado()

    implicitWidth: fila.implicitWidth + 30
    height: 40
    radius: 10
    color: activo ? Qt.alpha(T.ACENTO, oscuro ? 0.14 : 0.08)
         : zona.containsMouse ? T.ELEVADO : "transparent"
    border.color: activo ? Qt.alpha(T.ACENTO, 0.5) : T.BORDE
    Behavior on color { ColorAnimation { duration: 120 } }

    Row {
        id: fila
        anchors.centerIn: parent
        spacing: 6
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: desplegable.rotulo
            color: T.TINTA_MEDIA
            font.family: fuente
            font.pixelSize: 13
        }
        Text {
            anchors.verticalCenter: parent.verticalCenter
            text: desplegable.valor
            color: desplegable.activo ? T.ACENTO : T.TINTA
            font.family: fuente
            font.pixelSize: 13
            font.weight: Font.DemiBold
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
        id: zona
        anchors.fill: parent
        hoverEnabled: true
        cursorShape: Qt.PointingHandCursor
        onClicked: desplegable.pulsado()
    }
}
