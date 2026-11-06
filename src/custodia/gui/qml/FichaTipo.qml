// Ficha de color que identifica el tipo de un elemento de un vistazo: carpeta,
// PDF, hoja de cálculo, documento, imagen… El color sale de la familia del
// formato; la extensión se escribe dentro (o el icono de carpeta).
import QtQuick

Rectangle {
    id: ficha

    property bool esCarpeta: false
    property string ext: ""
    property bool cifrado: false
    property int lado: 36

    readonly property var familias: [
        { exts: ["pdf"], color: "#E5484D" },
        { exts: ["doc", "docx", "odt", "rtf"], color: "#3B82F6" },
        { exts: ["xls", "xlsx", "csv", "ods"], color: "#22A06B" },
        { exts: ["ppt", "pptx", "odp", "key"], color: "#F97316" },
        { exts: ["png", "jpg", "jpeg", "gif", "bmp", "webp", "svg", "heic"], color: "#A855F7" },
        { exts: ["zip", "rar", "7z", "tar", "gz"], color: "#D4A017" },
        { exts: ["mp3", "wav", "flac", "ogg", "m4a"], color: "#EC4899" },
        { exts: ["mp4", "mov", "avi", "mkv", "webm"], color: "#06B6D4" },
        { exts: ["txt", "md", "log", "json", "xml", "ini"], color: "#8B95A1" }
    ]
    readonly property color tono: {
        if (esCarpeta) return T.ACENTO
        for (const f of familias)
            if (f.exts.indexOf(ext) >= 0) return f.color
        return "#7C8794"
    }

    width: lado
    height: lado
    radius: lado * 0.28
    color: Qt.alpha(tono, oscuro ? 0.18 : 0.12)

    Text {
        anchors.centerIn: parent
        visible: ficha.esCarpeta
        text: ""
        font.family: iconos
        font.pixelSize: ficha.lado * 0.46
        color: ficha.tono
    }
    Text {
        anchors.centerIn: parent
        visible: !ficha.esCarpeta
        text: (ficha.ext || "?").substring(0, 4).toUpperCase()
        font.family: fuente
        font.pixelSize: Math.max(8, ficha.lado * (ficha.ext.length > 3 ? 0.22 : 0.26))
        font.weight: Font.Bold
        font.letterSpacing: 0.3
        color: ficha.tono
    }

    // Candado pequeño en la esquina si el contenido está cifrado.
    Rectangle {
        visible: ficha.cifrado
        width: ficha.lado * 0.44
        height: width
        radius: width / 2
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        anchors.rightMargin: -width * 0.22
        anchors.bottomMargin: -width * 0.22
        color: T.VERDE
        border.width: 2
        border.color: T.PANEL
        Text {
            anchors.centerIn: parent
            text: ""
            font.family: iconos
            font.pixelSize: parent.width * 0.48
            color: "white"
        }
    }
}
