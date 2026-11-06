// Selector de fechas para filtrar la bitácora: atajos a la izquierda y un
// calendario mensual a la derecha. Un clic elige un día; un segundo clic, el
// final del intervalo (con vista previa al pasar el ratón). Los días con
// actividad registrada llevan un punto; los futuros están apagados.
//
// Trabaja con fechas en texto AAAA-MM-DD ("" = sin límite) para no depender
// de zonas horarias.
import QtQuick
import QtQuick.Effects

Rectangle {
    id: cal

    property string desde: ""
    property string hasta: ""
    property var diasMarcados: []

    signal aplicado(string desde, string hasta)

    // Estado de la elección en curso.
    property string selA: ""
    property string selB: ""
    property bool eligiendo: false
    property string encima: ""
    property int anio: 2026
    property int mes: 0          // 0 = enero

    readonly property var mesesLargos: ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
                                        "agosto", "septiembre", "octubre", "noviembre", "diciembre"]
    readonly property var mesesCortos: ["ene", "feb", "mar", "abr", "may", "jun",
                                        "jul", "ago", "sep", "oct", "nov", "dic"]
    readonly property string hoy: iso(new Date())
    readonly property var marcados: {
        const m = {}
        for (const d of diasMarcados) m[d] = true
        return m
    }

    width: 600
    height: columna.implicitHeight + 40
    radius: 16
    color: T.PANEL
    border.color: T.BORDE

    layer.enabled: true
    layer.effect: MultiEffect {
        shadowEnabled: true
        shadowColor: "#000000"
        shadowOpacity: oscuro ? 0.6 : 0.18
        shadowBlur: 1.0
        blurMax: 40
        shadowVerticalOffset: 10
    }

    // ---- utilidades de fecha ---------------------------------------------------
    function dos(n) { return (n < 10 ? "0" : "") + n }
    function iso(f) { return f.getFullYear() + "-" + dos(f.getMonth() + 1) + "-" + dos(f.getDate()) }
    function deIso(t) { const p = t.split("-"); return new Date(+p[0], +p[1] - 1, +p[2]) }
    function sumarDias(t, n) { const f = deIso(t); f.setDate(f.getDate() + n); return iso(f) }
    function corto(t) { const f = deIso(t); return f.getDate() + " " + mesesCortos[f.getMonth()] + " " + f.getFullYear() }
    function describir(a, b) {
        if (!a && !b) return "Cualquier fecha"
        if (a && (!b || a === b)) return corto(a)
        const fa = deIso(a), fb = deIso(b)
        if (fa.getFullYear() === fb.getFullYear())
            return fa.getDate() + " " + mesesCortos[fa.getMonth()] + " – " + corto(b)
        return corto(a) + " – " + corto(b)
    }

    function abrir() {
        selA = desde
        selB = hasta
        eligiendo = false
        encima = ""
        const ref = deIso(hasta || desde || hoy)
        anio = ref.getFullYear()
        mes = ref.getMonth()
    }
    function moverMes(n) {
        let m = mes + n, a = anio
        while (m < 0) { m += 12; a-- }
        while (m > 11) { m -= 12; a++ }
        mes = m; anio = a
    }
    function elegir(d) {
        if (!eligiendo) {
            selA = d; selB = ""; eligiendo = true
        } else {
            if (d < selA) { selB = selA; selA = d } else selB = d
            eligiendo = false
        }
    }
    function enRango(d) {
        const b = eligiendo ? encima : selB
        if (!selA || !b) return false
        const lo = selA < b ? selA : b, hi = selA < b ? b : selA
        return d > lo && d < hi
    }
    function esExtremo(d) {
        return d === selA || d === (eligiendo ? encima : selB)
    }

    readonly property var atajos: {
        const h = hoy
        const f = deIso(h)
        const iniMes = iso(new Date(f.getFullYear(), f.getMonth(), 1))
        const iniAnt = iso(new Date(f.getFullYear(), f.getMonth() - 1, 1))
        const finAnt = iso(new Date(f.getFullYear(), f.getMonth(), 0))
        return [
            { t: "Hoy", a: h, b: h },
            { t: "Ayer", a: sumarDias(h, -1), b: sumarDias(h, -1) },
            { t: "Últimos 7 días", a: sumarDias(h, -6), b: h },
            { t: "Últimos 30 días", a: sumarDias(h, -29), b: h },
            { t: "Este mes", a: iniMes, b: h },
            { t: "Mes anterior", a: iniAnt, b: finAnt },
            { t: "Cualquier fecha", a: "", b: "" }
        ]
    }

    MouseArea { anchors.fill: parent; acceptedButtons: Qt.AllButtons }

    Column {
        id: columna
        x: 20
        y: 20
        width: parent.width - 40
        spacing: 16

        Row {
            width: parent.width
            spacing: 20

            // ---- atajos ----
            Column {
                id: atajosCol
                width: 150
                spacing: 2
                Repeater {
                    model: cal.atajos
                    Rectangle {
                        id: atajo
                        required property var modelData
                        readonly property bool actual: cal.desde === modelData.a && cal.hasta === modelData.b
                        width: atajosCol.width
                        height: 36
                        radius: 9
                        color: actual ? Qt.alpha(T.ACENTO, oscuro ? 0.16 : 0.10)
                             : zonaAtajo.containsMouse ? T.ELEVADO : "transparent"
                        Behavior on color { ColorAnimation { duration: 120 } }
                        Text {
                            x: 12
                            anchors.verticalCenter: parent.verticalCenter
                            text: atajo.modelData.t
                            color: atajo.actual ? T.ACENTO : T.TINTA
                            font.family: fuente
                            font.pixelSize: 13
                            font.weight: atajo.actual ? Font.DemiBold : Font.Normal
                        }
                        MouseArea {
                            id: zonaAtajo
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            // Un atajo se aplica al momento.
                            onClicked: cal.aplicado(atajo.modelData.a, atajo.modelData.b)
                        }
                    }
                }
            }

            Rectangle { width: 1; height: mesCol.height; color: T.BORDE_SUAVE }

            // ---- calendario ----
            Column {
                id: mesCol
                width: parent.width - atajosCol.width - 41
                spacing: 8

                Item {
                    width: parent.width
                    height: 34
                    IconoBoton {
                        anchors.left: parent.left
                        anchors.verticalCenter: parent.verticalCenter
                        lado: 32
                        glifo: ""
                        tamGlifo: 11
                        pista: "Mes anterior"
                        onPulsado: cal.moverMes(-1)
                    }
                    Text {
                        anchors.centerIn: parent
                        text: cal.mesesLargos[cal.mes].charAt(0).toUpperCase() + cal.mesesLargos[cal.mes].slice(1) + " " + cal.anio
                        color: T.TINTA
                        font.family: fuente
                        font.pixelSize: 15
                        font.weight: Font.DemiBold
                    }
                    IconoBoton {
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        lado: 32
                        glifo: ""
                        tamGlifo: 11
                        pista: "Mes siguiente"
                        activo: cal.iso(new Date(cal.anio, cal.mes + 1, 1)) <= cal.hoy
                        onPulsado: cal.moverMes(1)
                    }
                }

                // Días de la semana (empieza en lunes).
                Row {
                    Repeater {
                        model: ["L", "M", "X", "J", "V", "S", "D"]
                        Text {
                            required property string modelData
                            width: mesCol.width / 7
                            horizontalAlignment: Text.AlignHCenter
                            text: modelData
                            color: T.TINTA_TENUE
                            font.family: fuente
                            font.pixelSize: 11
                            font.weight: Font.DemiBold
                        }
                    }
                }

                Grid {
                    id: rejilla
                    columns: 7
                    readonly property int desfase: (new Date(cal.anio, cal.mes, 1).getDay() + 6) % 7
                    readonly property int diasMes: new Date(cal.anio, cal.mes + 1, 0).getDate()
                    Repeater {
                        model: 42
                        Item {
                            id: celda
                            required property int index
                            readonly property int dia: index - rejilla.desfase + 1
                            readonly property bool valido: dia >= 1 && dia <= rejilla.diasMes
                            readonly property string fecha: valido ? cal.iso(new Date(cal.anio, cal.mes, dia)) : ""
                            readonly property bool futuro: valido && fecha > cal.hoy
                            readonly property bool extremo: valido && cal.esExtremo(fecha)
                            readonly property bool dentro: valido && cal.enRango(fecha)
                            width: mesCol.width / 7
                            height: 36
                            visible: index < Math.ceil((rejilla.desfase + rejilla.diasMes) / 7) * 7

                            // Banda del intervalo.
                            Rectangle {
                                anchors.verticalCenter: parent.verticalCenter
                                width: parent.width
                                height: 32
                                visible: celda.dentro
                                color: Qt.alpha(T.ACENTO, oscuro ? 0.16 : 0.10)
                            }
                            Rectangle {
                                anchors.centerIn: parent
                                width: 34; height: 34; radius: 17
                                visible: celda.valido
                                color: celda.extremo ? T.ACENTO
                                     : zonaDia.containsMouse && !celda.futuro ? T.ELEVADO : "transparent"
                                border.width: celda.fecha === cal.hoy && !celda.extremo ? 1 : 0
                                border.color: T.ACENTO
                                Text {
                                    anchors.centerIn: parent
                                    text: celda.dia
                                    color: celda.extremo ? "white" : celda.futuro ? T.TINTA_TENUE : T.TINTA
                                    opacity: celda.futuro ? 0.5 : 1
                                    font.family: fuente
                                    font.pixelSize: 13
                                    font.weight: celda.extremo || celda.fecha === cal.hoy ? Font.DemiBold : Font.Normal
                                }
                                // Punto: hay actividad registrada ese día.
                                Rectangle {
                                    visible: !!cal.marcados[celda.fecha]
                                    anchors.horizontalCenter: parent.horizontalCenter
                                    anchors.bottom: parent.bottom
                                    anchors.bottomMargin: 4
                                    width: 4; height: 4; radius: 2
                                    color: celda.extremo ? "white" : T.ACENTO
                                }
                            }
                            MouseArea {
                                id: zonaDia
                                anchors.fill: parent
                                enabled: celda.valido && !celda.futuro
                                hoverEnabled: true
                                cursorShape: Qt.PointingHandCursor
                                onContainsMouseChanged: if (containsMouse) cal.encima = celda.fecha
                                onClicked: cal.elegir(celda.fecha)
                            }
                        }
                    }
                }
            }
        }

        Rectangle { width: parent.width; height: 1; color: T.BORDE_SUAVE }

        Item {
            width: parent.width
            height: 40
            Column {
                anchors.verticalCenter: parent.verticalCenter
                spacing: 1
                Text {
                    text: cal.eligiendo ? "Elige el último día" : cal.describir(cal.selA, cal.selB || cal.selA)
                    color: T.TINTA
                    font.family: fuente
                    font.pixelSize: 13
                    font.weight: Font.DemiBold
                }
                Text {
                    text: cal.eligiendo ? "o vuelve a pulsar el mismo para un solo día"
                                        : "Un clic elige un día; dos, un intervalo"
                    color: T.TINTA_TENUE
                    font.family: fuente
                    font.pixelSize: 11
                }
            }
            Row {
                anchors.right: parent.right
                anchors.verticalCenter: parent.verticalCenter
                spacing: 8
                Boton {
                    height: 38
                    primario: false
                    texto: "Limpiar"
                    onPulsado: cal.aplicado("", "")
                }
                Boton {
                    height: 38
                    texto: "Aplicar"
                    opacity: cal.selA ? 1 : 0.5
                    onPulsado: {
                        if (!cal.selA) return
                        const b = cal.eligiendo ? cal.selA : (cal.selB || cal.selA)
                        cal.aplicado(cal.selA, b)
                    }
                }
            }
        }
    }
}
