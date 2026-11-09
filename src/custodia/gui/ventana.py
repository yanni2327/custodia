# -*- coding: utf-8 -*-
"""
Ventana principal.

La interfaz se dibuja en QML (``qml/Principal.qml``) dentro de un
`QQuickWidget`. La ventana en sí sigue siendo una `QMainWindow` de widgets por
dos razones prácticas durante la migración:

- los diálogos (permisos, cuentas, bitácora, avisos) todavía son widgets y
  necesitan una ventana-widget como padre;
- la pantalla de bloqueo es una capa de widgets que se pone encima.

Reparto de responsabilidades:

- **QML** pinta, anima y avisa de lo que la persona hace (clic en una carpeta,
  selección, botón de una acción), llamando a `PuentePrincipal`.
- **Esta clase** decide qué hacer: habla con la sesión, abre los diálogos y
  publica en el puente los datos que QML muestra (árbol, listado, panel…).

La decisión de diseño que manda sobre las demás sigue en pie: **el panel de
permisos está siempre visible** y se actualiza al seleccionar cualquier cosa.

Sobre los metadatos: el nombre, el tamaño y la fecha los obtiene la sesión bajo
suplantación, porque son parte del listado. El propietario, en cambio, lo lee
la aplicación: hay que poder mostrarlo incluso en elementos que el usuario no
puede abrir.
"""
from __future__ import annotations

import threading
from pathlib import Path

from PySide6.QtCore import (Property, QEventLoop, QObject, QSettings, QTimer,
                            QUrl, Signal, Slot)
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtQuickWidgets import QQuickWidget
from PySide6.QtWidgets import QApplication, QDialog, QFileDialog, QMainWindow

from ..core import config
from ..core.errors import (AuthenticationError, CustodiaError, PermissionDenied,
                           SegundoFactorRequerido)
from ..core.permissions import Accion
from . import avisos, estilo
from .bloqueo import VigilanteInactividad
from .hojas import (ControladorBitacora, ControladorContrasena, ControladorCuentas,
                    ControladorPermisos, ControladorRespaldo,
                    ControladorSegundoFactor)
from .qmlbase import CARPETA_QML, actualizar_tema, preparar_contexto
from .sesion import Sesion

#: Cómo se nombra cada permiso en pantalla. La enumeración usa términos del
#: dominio; aquí se traducen a lo que la persona entiende que está haciendo.
_ETIQUETAS = {
    Accion.LEER: "Abrir y leer",
    Accion.ESCRIBIR: "Modificar",
    Accion.LISTAR: "Ver el contenido",
    Accion.CREAR: "Crear dentro",
    Accion.ELIMINAR: "Eliminar",
    Accion.CAMBIAR_PERMISOS: "Cambiar permisos",
}

_ORDEN = [Accion.LEER, Accion.ESCRIBIR, Accion.LISTAR, Accion.CREAR,
          Accion.ELIMINAR, Accion.CAMBIAR_PERMISOS]


_MESES = ["ene", "feb", "mar", "abr", "may", "jun",
          "jul", "ago", "sep", "oct", "nov", "dic"]


def _fecha(iso: str) -> str:
    """'2026-11-04T10:32:..' → '4 nov 2026, 10:32' (más legible que ISO)."""
    try:
        fecha, hora = iso[:16].split("T")
        anio, mes, dia = fecha.split("-")
        return f"{int(dia)} {_MESES[int(mes) - 1]} {anio}, {hora}"
    except (ValueError, IndexError):
        return iso[:16].replace("T", " ")


def _legible(nodo) -> str:
    """Tamaño en unidades que una persona lee de un vistazo."""
    if nodo.es_carpeta:
        return "—"
    tam = nodo.tamano_claro if nodo.tamano_claro is not None else nodo.tamano
    for unidad in ("B", "KB", "MB", "GB"):
        if tam < 1024 or unidad == "GB":
            return f"{tam:.0f} {unidad}" if unidad == "B" else f"{tam:.1f} {unidad}"
        tam /= 1024
    return ""


class PuentePrincipal(QObject):
    """
    Lo que QML ve como `puente`: datos de solo lectura y acciones.

    Cada dato tiene su propia señal de cambio, para que al seleccionar un
    archivo (que solo cambia el panel) no se reconstruya el listado entero.
    """

    arbolChanged = Signal()
    archivosChanged = Signal()
    vistaChanged = Signal()
    cabeceraChanged = Signal()
    panelChanged = Signal()
    seleccionChanged = Signal()
    rutaActualChanged = Signal()
    versionIconosChanged = Signal()
    modalChanged = Signal()
    bloqueoChanged = Signal()
    hojaChanged = Signal()
    perfilChanged = Signal()

    #: Mensaje breve tras una acción ("Carpeta creada").
    notificacion = Signal(str)
    #: Respuestas de la pantalla de bloqueo.
    desbloqueoError = Signal(str)
    desbloqueoPideCodigo = Signal()
    desbloqueoOcupado = Signal(bool)
    #: Uso interno: resultado del hilo de desbloqueo.
    _resultadoDesbloqueo = Signal(object)

    def __init__(self, ventana: "VentanaPrincipal") -> None:
        super().__init__(ventana)
        self._v = ventana
        self._datos = {
            "arbol": [], "archivos": [], "vista": {"modo": "lista"},
            "cabecera": {"titulo": "", "subtitulo": "", "migas": []},
            "panel": {"elemento": "", "propietario": "", "permisos": []},
            "seleccion": "", "rutaActual": "/", "versionIconos": 0,
            "modal": {}, "bloqueo": {"activo": False}, "hoja": "",
            "perfil": {"dosPasos": False},
        }
        self._ctrl_hoja: QObject | None = None
        self._resultadoDesbloqueo.connect(ventana._al_resultado_desbloqueo)

    def publicar(self, clave: str, valor) -> None:
        self._datos[clave] = valor
        getattr(self, clave + "Changed").emit()

    # -- propiedades --------------------------------------------------------

    def _g(clave):   # noqa: N805 — fábrica de getters, no método
        return lambda self: self._datos[clave]

    arbol = Property("QVariantList", _g("arbol"), notify=arbolChanged)
    archivos = Property("QVariantList", _g("archivos"), notify=archivosChanged)
    vista = Property("QVariantMap", _g("vista"), notify=vistaChanged)
    cabecera = Property("QVariantMap", _g("cabecera"), notify=cabeceraChanged)
    panel = Property("QVariantMap", _g("panel"), notify=panelChanged)
    seleccion = Property(str, _g("seleccion"), notify=seleccionChanged)
    rutaActual = Property(str, _g("rutaActual"), notify=rutaActualChanged)
    versionIconos = Property(int, _g("versionIconos"), notify=versionIconosChanged)
    modal = Property("QVariantMap", _g("modal"), notify=modalChanged)
    bloqueo = Property("QVariantMap", _g("bloqueo"), notify=bloqueoChanged)
    #: Hoja de administración abierta ("cuentas", "bitacora"…; "" = ninguna).
    hoja = Property(str, _g("hoja"), notify=hojaChanged)
    #: Estado de seguridad de la cuenta, para el panel de perfil.
    perfil = Property("QVariantMap", _g("perfil"), notify=perfilChanged)
    del _g

    @Slot()
    def refrescarPerfil(self) -> None:
        self._v._actualizar_perfil()

    def _get_ctrl(self):
        return self._ctrl_hoja

    #: Controlador de la hoja abierta (ver hojas.py).
    ctrl = Property(QObject, _get_ctrl, notify=hojaChanged)

    @Slot(str)
    def copiarTexto(self, texto: str) -> None:
        """
        Copia un dato sensible (contraseña temporal) y lo borra del
        portapapeles al minuto, para que no quede a la vista de otras apps.
        """
        from PySide6.QtGui import QGuiApplication
        portapapeles = QGuiApplication.clipboard()
        portapapeles.setText(texto)

        def limpiar() -> None:
            if portapapeles.text() == texto:
                portapapeles.clear()

        QTimer.singleShot(60_000, limpiar)
        self._v._notificar("Copiada; se borrará del portapapeles en un minuto")

    @Slot()
    def cerrarHoja(self) -> None:
        QTimer.singleShot(0, self._v._cerrar_hoja)

    @Property(str, constant=True)
    def usuario(self) -> str:
        return self._v.sesion.username

    @Property(bool, constant=True)
    def esAdmin(self) -> bool:
        return self._v.sesion.es_admin

    # -- llamadas desde QML -------------------------------------------------
    # Todo lo que puede abrir un diálogo se difiere un ciclo del bucle de
    # eventos: así el manejador de QML termina antes de que empiece el diálogo
    # modal, y no queda un clic "a medias" dentro de QML mientras tanto.

    @Slot(str)
    def abrir(self, ruta: str) -> None:
        QTimer.singleShot(0, lambda: self._v._abrir(ruta))

    @Slot(str, bool)
    def seleccionar(self, ruta: str, es_carpeta: bool) -> None:
        self._v._seleccionar(ruta, es_carpeta)

    @Slot(str)
    def accion(self, nombre: str) -> None:
        QTimer.singleShot(0, lambda: self._v._accion(nombre))

    @Slot("QVariantList")
    def soltarArchivos(self, urls: list) -> None:
        rutas = [QUrl(u).toLocalFile() if not isinstance(u, QUrl) else u.toLocalFile()
                 for u in urls]
        rutas = [r for r in rutas if r and Path(r).is_file()]
        if rutas:
            QTimer.singleShot(0, lambda: self._v._subir(rutas))

    @Slot("QVariant")
    def responder(self, valor) -> None:
        """Respuesta de un aviso o pregunta mostrados en QML."""
        self._v._responder_modal(valor)

    @Slot(str, str)
    def desbloquear(self, password: str, codigo: str) -> None:
        self._v._desbloquear(password, codigo or None)

    @Slot()
    def cerrarSesionDesdeBloqueo(self) -> None:
        QTimer.singleShot(0, self._v._cerrar_sesion)


class VentanaPrincipal(QMainWindow):

    def __init__(self, sesion: Sesion) -> None:
        super().__init__()
        self.sesion = sesion
        #: True si la ventana se cerró con «Cerrar sesión» (volver al login)
        #: en vez de con la X (salir de la aplicación).
        self.cerro_sesion = False
        self.ruta_actual = "/"
        self.ruta_seleccionada = "/"
        self._seleccion: tuple[str, bool] | None = None
        self._app = QApplication.instance()
        self._ajustes = QSettings("Custodia", "Custodia")

        self.setWindowTitle("Custodia")
        # Tamaño inicial que nunca exceda la pantalla (p. ej. 1366×768).
        disponible = self.screen().availableGeometry()
        self.resize(min(1280, disponible.width() - 40),
                    min(780, disponible.height() - 40))
        # Mínimo pensado para caber en una pantalla de 1366×768 con la barra
        # de tareas; en esas pantallas el panel de permisos se desplaza.
        self.setMinimumSize(1000, 600)

        self.puente = PuentePrincipal(self)
        self._construir()
        self._cargar_arbol()
        self._abrir("/")
        self._actualizar_perfil()
        self._preparar_bloqueo()
        QTimer.singleShot(0, self._avisar_clave_no_disponible)

    def _avisar_clave_no_disponible(self) -> None:
        """Modo de recuperación: la clave maestra está dañada o falta."""
        if self.sesion.clave_disponible():
            return
        if self.sesion.es_admin:
            avisos.advertencia(
                self, "La clave maestra no está disponible",
                "No se puede abrir la clave de cifrado de este equipo y los "
                "archivos cifrados no se pueden leer. Abre tu perfil y entra en "
                "«Respaldo de la clave» para restaurar un respaldo."
            )
        else:
            avisos.advertencia(
                self, "La clave maestra no está disponible",
                "Los archivos cifrados no se pueden abrir por ahora. Avisa a un "
                "administrador de Custodia para que restaure el respaldo."
            )

    # -- construcción -------------------------------------------------------

    def _construir(self) -> None:
        self.vista = QQuickWidget(self)
        self.vista.setResizeMode(QQuickWidget.ResizeMode.SizeRootObjectToView)
        # Mientras QML arranca se ve el color de fondo del tema, no un blanco.
        self.vista.setClearColor(estilo.paleta().window().color())

        ctx = self.vista.rootContext()
        preparar_contexto(self.vista.engine(), ctx)
        ctx.setContextProperty("puente", self.puente)

        self.vista.setSource(QUrl.fromLocalFile(str(CARPETA_QML / "Principal.qml")))
        if self.vista.status() == QQuickWidget.Status.Error:
            raise RuntimeError("No se pudo cargar Principal.qml:\n" + "\n".join(
                e.toString() for e in self.vista.errors()))
        self.setCentralWidget(self.vista)

    # -- bloqueo por inactividad -------------------------------------------

    def _preparar_bloqueo(self) -> None:
        """
        Bloqueo automático tras `BLOQUEO_INACTIVIDAD_MIN` minutos sin uso,
        manual con Ctrl+L, y cierre de sesión si la pantalla sigue bloqueada
        `SESSION_IDLE_MINUTES` minutos más.
        """
        self._vigilante = VigilanteInactividad(config.BLOQUEO_INACTIVIDAD_MIN, self)
        self._vigilante.inactivo.connect(lambda: self.bloquear(automatico=True))
        self._vigilante.iniciar(self._app)

        self._expiracion = QTimer(self)
        self._expiracion.setSingleShot(True)
        self._expiracion.setInterval(max(config.SESSION_IDLE_MINUTES, 1) * 60_000)
        self._expiracion.timeout.connect(self._expirar)

        QShortcut(QKeySequence("Ctrl+L"), self, activated=self.bloquear)

    @property
    def _bloqueada(self) -> bool:
        return bool(self.puente.bloqueo.get("activo"))

    def bloquear(self, automatico: bool = False) -> None:
        """Tapa la ventana y exige la contraseña para continuar."""
        if self._bloqueada:
            return
        self._vigilante.pausar()

        # Cerrar menús, avisos y diálogos abiertos: si no, seguirían
        # mostrando contenido por encima de la capa de bloqueo. Cerrarlos
        # equivale a cancelarlos, así que ninguna acción a medias se completa.
        self._responder_modal(None)
        emergente = QApplication.activePopupWidget()
        if emergente is not None:
            emergente.close()
        for widget in QApplication.topLevelWidgets():
            if isinstance(widget, QDialog) and widget.isVisible():
                widget.reject()
        raiz = self.vista.rootObject()
        if raiz is not None:
            raiz.cerrarMenus()

        if automatico:
            motivo = (f"Se bloqueó tras {config.BLOQUEO_INACTIVIDAD_MIN} minutos "
                      "sin actividad. Escribe tu contraseña para continuar.")
        else:
            motivo = "Escribe tu contraseña para continuar."
        self.sesion.registrar_bloqueo("inactividad" if automatico else "manual")
        self.puente.publicar("bloqueo", {"activo": True, "motivo": motivo})
        if config.SESSION_IDLE_MINUTES > 0:
            self._expiracion.start()

    def _desbloquear(self, password: str, codigo: str | None) -> None:
        """
        Comprueba la contraseña en un hilo aparte: `LogonUser` tarda a
        propósito cuando falla, y en el hilo de la interfaz congelaría la
        animación de espera. El hilo no suplanta a nadie.
        """
        if not self._bloqueada or getattr(self, "_comprobando", False):
            return
        self._comprobando = True
        self.puente.desbloqueoOcupado.emit(True)

        def trabajo() -> None:
            try:
                self.sesion.desbloquear(password, codigo)
                resultado = ("ok", "")
            except SegundoFactorRequerido:
                resultado = ("codigo", "")
            except AuthenticationError as exc:
                resultado = ("error", str(exc))
            except Exception as exc:
                resultado = ("error", f"No se pudo comprobar: {exc}")
            self.puente._resultadoDesbloqueo.emit(resultado)

        threading.Thread(target=trabajo, name="custodia-desbloqueo",
                         daemon=True).start()

    def _al_resultado_desbloqueo(self, resultado: tuple) -> None:
        self._comprobando = False
        self.puente.desbloqueoOcupado.emit(False)
        tipo, mensaje = resultado
        if tipo == "ok":
            self._expiracion.stop()
            self.puente.publicar("bloqueo", {"activo": False})
            self._vigilante.reanudar()
        elif tipo == "codigo":
            self.puente.desbloqueoPideCodigo.emit()
        elif self.sesion.cuenta_bloqueada():
            # Demasiados intentos: no se deja seguir probando desde aquí.
            self._cerrar_sesion()
        else:
            self.puente.desbloqueoError.emit(mensaje)

    def _expirar(self) -> None:
        """La pantalla siguió bloqueada demasiado tiempo: se cierra la sesión."""
        if self._bloqueada:
            self._cerrar_sesion()

    # -- avisos dentro de la ventana -----------------------------------------

    def preguntar(self, datos: dict, validar=None):
        """
        Muestra un aviso o pregunta en QML y espera la respuesta.

        Lo usa `avisos` cuando el padre es esta ventana. Devuelve lo que QML
        responda ({"ok": bool, "texto": str}) o None si se canceló.

        `validar(respuesta)`, si se da, se llama al aceptar: devuelve "" si la
        respuesta vale, un mensaje para mostrarlo en la misma ventana y dejar
        que la persona lo intente otra vez, o None para cerrar sin aceptar.
        """
        if getattr(self, "_bucle_modal", None) is not None or self._bloqueada:
            return None
        self._bucle_modal = QEventLoop()
        intento = 0
        try:
            while True:
                self._respuesta_modal = None
                self.puente.publicar("modal", {**datos, "intento": intento})
                self._bucle_modal.exec()
                respuesta = self._respuesta_modal
                if validar is None or not respuesta or not respuesta.get("ok"):
                    return respuesta
                error = validar(respuesta)
                if error == "":
                    return respuesta
                if error is None:
                    return None
                intento += 1
                datos = {**datos, "error": error}
        finally:
            self._bucle_modal = None
            self.puente.publicar("modal", {})

    def _confirmar_con_codigo(self, titulo: str, mensaje: str, operacion: str,
                              aceptar: str = "Confirmar",
                              peligro: bool = False) -> bool:
        """
        Pide el código de la app de autenticación antes de una operación
        sensible. Es la ÚNICA puerta para eliminar, descargar, subir, renombrar,
        cambiar permisos y administrar cuentas.

        - Sin segundo factor activado, la operación no se hace: se ofrece
          activarlo en ese momento.
        - Un código incorrecto se avisa en la misma ventana; cada fallo cuenta
          para el bloqueo de la cuenta y, si se alcanza el límite, la sesión
          se cierra.
        - `operacion` queda en la bitácora junto al resultado.
        """
        if not self.sesion.segundo_factor_activo():
            if avisos.confirmar(
                self, "Activa la verificación en dos pasos",
                "Para hacer esto hay que confirmar con el código de tu app de "
                "autenticación, y tu cuenta todavía no la tiene configurada. "
                "Se activa en un minuto escaneando un código QR con el teléfono.",
                aceptar="Activarla ahora", cancelar="Ahora no",
            ):
                self._abrir_segundo_factor()
            return False

        bloqueada = {"motivo": ""}

        def validar(respuesta: dict):
            try:
                resultado = self.sesion.confirmar_operacion(
                    respuesta.get("texto", ""), operacion)
            except AuthenticationError as exc:
                bloqueada["motivo"] = str(exc)
                return None
            if resultado == "ok":
                return ""
            if resultado == "usado":
                return ("Ese código ya se usó. Espera a que tu app muestre uno "
                        "nuevo (cambia cada 30 segundos).")
            return "El código no es correcto. Escribe el que muestra ahora tu app."

        respuesta = self.preguntar({
            "tipo": "codigo", "titulo": titulo, "mensaje": mensaje,
            "aceptar": aceptar, "cancelar": "Cancelar", "peligro": peligro,
        }, validar=validar)

        if bloqueada["motivo"]:
            avisos.error(self, "Sesión cerrada por seguridad", bloqueada["motivo"])
            QTimer.singleShot(0, self._cerrar_sesion)
            return False
        return bool(respuesta and respuesta.get("ok"))

    def _responder_modal(self, valor) -> None:
        bucle = getattr(self, "_bucle_modal", None)
        if bucle is None:
            return
        self._respuesta_modal = dict(valor) if valor else None
        bucle.quit()

    def _notificar(self, texto: str) -> None:
        self.puente.notificacion.emit(texto)

    # -- tema ---------------------------------------------------------------

    def _alternar_tema(self) -> None:
        nombre = "claro" if estilo.TEMA_ACTUAL == "oscuro" else "oscuro"
        estilo.aplicar(nombre)
        # Paleta y hoja de estilo siguen haciendo falta para los diálogos de
        # widgets y la pantalla de bloqueo.
        self._app.setPalette(estilo.paleta())
        self._app.setStyleSheet(estilo.HOJA)
        self._ajustes.setValue("tema", nombre)
        for ventana in QApplication.topLevelWidgets():
            estilo.tenir_barra_titulo(ventana, nombre == "oscuro")
        # QML anima solo el cambio de colores; los iconos dibujados se piden
        # de nuevo porque su color también depende del tema.
        actualizar_tema(self.vista.rootContext())
        self.puente.publicar("versionIconos", self.puente.versionIconos + 1)

    # -- carga de datos -----------------------------------------------------

    def _cargar_arbol(self) -> None:
        filas = [{"ruta": "/", "nombre": "Almacén", "nivel": 0, "hijos": False}]
        self._llenar_rama(filas, "/", 1)
        filas[0]["hijos"] = len(filas) > 1
        self.puente.publicar("arbol", filas)

    def _llenar_rama(self, filas: list, ruta: str, nivel: int) -> None:
        try:
            nodos = self.sesion.listar(ruta)
        except CustodiaError:
            return   # sin permiso para ver el contenido: la rama queda vacía

        for nodo in nodos:
            if not nodo.es_carpeta:
                continue
            # Un usuario normal no debería ver ni el nombre de las carpetas
            # ajenas. El kernel ya le niega el acceso (queda en la bitácora);
            # además se ocultan aquí las que ni siquiera puede listar. De paso
            # se evita llenar la bitácora de negaciones al construir el árbol,
            # porque no se recorre lo que no se puede abrir.
            if not self.sesion.es_admin:
                try:
                    if Accion.LISTAR not in self.sesion.permisos_efectivos(nodo.ruta):
                        continue
                except Exception:
                    continue
            fila = {"ruta": nodo.ruta, "nombre": nodo.nombre, "nivel": nivel,
                    "hijos": False}
            filas.append(fila)
            antes = len(filas)
            self._llenar_rama(filas, nodo.ruta, nivel + 1)
            fila["hijos"] = len(filas) > antes

    def _abrir(self, ruta: str) -> None:
        self.ruta_actual = ruta
        self._seleccion = None
        self.puente.publicar("rutaActual", ruta)
        self.puente.publicar("seleccion", "")

        # Migas de pan: cada tramo es clicable.
        migas = [{"nombre": "Inicio", "ruta": "/"}]
        acumulada = ""
        for parte in ruta.strip("/").split("/") if ruta != "/" else []:
            acumulada += "/" + parte
            migas.append({"nombre": parte, "ruta": acumulada})
        titulo = "Almacén" if ruta == "/" else migas[-1]["nombre"]

        # El panel se pinta ANTES del listado, y pase lo que pase. Si la
        # carpeta está vetada, el panel es justamente donde está la
        # explicación; dejarlo en blanco al fallar convertía una denegación
        # legítima en un programa que parece roto.
        self._mostrar_permisos(ruta)

        def cabecera(subtitulo: str) -> None:
            self.puente.publicar("cabecera", {"titulo": titulo,
                                              "subtitulo": subtitulo,
                                              "migas": migas})

        try:
            nodos = self.sesion.listar(ruta)
        except PermissionDenied:
            cabecera("No tienes acceso a esta carpeta")
            self._vista_vacia(
                "Carpeta protegida",
                "Tu cuenta no tiene permiso para ver el contenido de esta "
                "carpeta. En el panel de la derecha puedes consultar qué sí "
                "puedes hacer aquí.",
                tipo="candado")
            return
        except CustodiaError as exc:
            cabecera("No se pudo abrir")
            self._vista_vacia("No se pudo abrir",
                              f"La carpeta no pudo abrirse. {exc}", tipo="error")
            return

        if ruta == "/" and not self.sesion.es_admin:
            cabecera("Tu carpeta personal y la carpeta compartida")
        else:
            cabecera(f"{len(nodos)} elemento{'s' if len(nodos) != 1 else ''}"
                     if nodos else "Carpeta vacía")

        if not nodos:
            # Sólo se ofrecen acciones donde el usuario realmente puede crear.
            puede_crear = (self.sesion.es_admin or
                           Accion.CREAR in self.sesion.permisos_efectivos(ruta))
            self._vista_vacia(
                "Carpeta vacía",
                "Aún no hay nada aquí. Crea una carpeta o añade un archivo "
                "para empezar. También puedes arrastrar archivos a esta ventana."
                if puede_crear else "Aún no hay nada en esta carpeta.",
                tipo="carpeta", con_acciones=puede_crear)
            return

        # Carpetas primero, luego archivos; dentro de cada grupo, por nombre.
        nodos = sorted(nodos, key=lambda n: (not n.es_carpeta, n.nombre.lower()))
        self.puente.publicar("archivos", [{
            "nombre": n.nombre,
            "ruta": n.ruta,
            "esCarpeta": n.es_carpeta,
            "ext": "" if n.es_carpeta else Path(n.nombre).suffix.lstrip(".").lower(),
            "tamano": _legible(n),
            "modificado": _fecha(n.modificado),
            "cifrado": bool(n.cifrado),
        } for n in nodos])
        self.puente.publicar("vista", {"modo": "lista"})

    def _vista_vacia(self, titulo: str, mensaje: str, tipo: str = "info",
                     con_acciones: bool = False) -> None:
        self.puente.publicar("archivos", [])
        self.puente.publicar("vista", {"modo": "vacia", "titulo": titulo,
                                       "texto": mensaje, "tipo": tipo,
                                       "acciones": con_acciones})

    def _mostrar_permisos(self, ruta: str) -> None:
        """RF-07: propietario y permisos efectivos del usuario actual."""
        self.ruta_seleccionada = ruta
        try:
            propietario = self.sesion.propietario(ruta)
        except Exception:
            propietario = "No se pudo leer"
        try:
            permitidas = self.sesion.permisos_efectivos(ruta)
        except Exception:
            # Ni siquiera se pudo consultar. Se pintan todas como negadas, que
            # es la lectura correcta: no hay nada que esta cuenta pueda hacer.
            permitidas = set()

        self.puente.publicar("panel", {
            "elemento": "Almacén" if ruta == "/" else Path(ruta).name,
            "propietario": propietario,
            "permisos": [{"etiqueta": _ETIQUETAS[a], "concedido": a in permitidas}
                         for a in _ORDEN],
        })

    # -- reacciones ---------------------------------------------------------

    def _seleccionar(self, ruta: str, es_carpeta: bool) -> None:
        """Selección en el listado; ruta vacía = nada (vuelve la carpeta)."""
        if ruta:
            self._seleccion = (ruta, es_carpeta)
            self.puente.publicar("seleccion", ruta)
            self._mostrar_permisos(ruta)
        else:
            self._seleccion = None
            self.puente.publicar("seleccion", "")
            self._mostrar_permisos(self.ruta_actual)

    def _accion(self, nombre: str) -> None:
        acciones = {
            "nuevaCarpeta": self._nueva_carpeta,
            "subir": self._subir,
            "descargar": self._descargar,
            "renombrar": self._renombrar,
            "eliminar": self._eliminar,
            "permisos": self._abrir_permisos,
            "cuentas": self._abrir_cuentas,
            "bitacora": self._abrir_bitacora,
            "respaldo": self._abrir_respaldo,
            "segundoFactor": self._abrir_segundo_factor,
            "contrasena": lambda: self._abrir_hoja("contrasena", ControladorContrasena(self)),
            "tema": self._alternar_tema,
            "bloquear": self.bloquear,
            "cerrarSesion": self._cerrar_sesion,
        }
        manejador = acciones.get(nombre)
        if manejador is not None:
            manejador()

    # -- hojas de administración ----------------------------------------------

    def _abrir_hoja(self, nombre: str, ctrl: QObject, al_cerrar=None) -> None:
        """Muestra una hoja (panel QML) con su controlador."""
        self._cerrar_hoja()
        self._al_cerrar_hoja = al_cerrar
        # Diferido: la señal llega desde un manejador de QML de la propia hoja,
        # y cerrarla en ese instante destruiría la vista mientras se ejecuta.
        ctrl.cerrar.connect(lambda: QTimer.singleShot(0, self._cerrar_hoja))
        self.puente._ctrl_hoja = ctrl
        self.puente.publicar("hoja", nombre)

    def _cerrar_hoja(self) -> None:
        ctrl = self.puente._ctrl_hoja
        if ctrl is None:
            return
        self.puente._ctrl_hoja = None
        self.puente.publicar("hoja", "")
        ctrl.al_cerrar()
        # Se libera más tarde: QML puede estar terminando la animación de
        # salida con los datos de este controlador.
        QTimer.singleShot(600, ctrl.deleteLater)
        al_cerrar, self._al_cerrar_hoja = getattr(self, "_al_cerrar_hoja", None), None
        if al_cerrar is not None:
            al_cerrar()
        self._actualizar_perfil()

    def _actualizar_perfil(self) -> None:
        """Estado de la verificación en dos pasos y de la clave de confirmación."""
        try:
            estado = {"dosPasos": bool(self.sesion.segundo_factor_activo())}
        except Exception:
            estado = {"dosPasos": False}
        self.puente.publicar("perfil", estado)

    def _abrir_segundo_factor(self) -> None:
        """
        Activar o desactivar el segundo factor de la propia cuenta.

        No necesita ser administrador: cada quien protege su propia cuenta.
        """
        self._abrir_hoja("segundoFactor", ControladorSegundoFactor(self))

    def _abrir_permisos(self) -> None:
        """
        Abierto para cualquiera: quien decide si puede cambiar algo es el
        kernel al escribir la DACL, no esta ventana. Un usuario normal puede
        editar los permisos de su propia carpeta, porque es su propietario.
        """
        ruta = self.ruta_seleccionada
        self._abrir_hoja("permisos", ControladorPermisos(self, ruta),
                         al_cerrar=lambda: self._mostrar_permisos(ruta))

    def _abrir_cuentas(self) -> None:
        if not self.sesion.es_admin:
            self._solo_admin("administrar cuentas y grupos")
            return
        self._abrir_hoja("cuentas", ControladorCuentas(self),
                         al_cerrar=self._cargar_arbol)

    def _abrir_bitacora(self) -> None:
        if not self.sesion.es_admin:
            self._solo_admin("consultar la bitácora")
            return
        self._abrir_hoja("bitacora", ControladorBitacora(self))

    def _abrir_respaldo(self) -> None:
        if not self.sesion.es_admin:
            self._solo_admin("exportar o restaurar el respaldo de la clave")
            return
        self._abrir_hoja("respaldo", ControladorRespaldo(self))

    def _solo_admin(self, que: str) -> None:
        avisos.info(
            self, "Hace falta ser administrador",
            f"Para {que} hay que pertenecer al grupo de administradores de "
            "Custodia. Tu cuenta no está en él."
        )

    # -- acciones sobre archivos --------------------------------------------

    def _en_raiz_sin_permiso(self) -> bool:
        """Un usuario normal no crea nada en la raíz: lo avisa y devuelve True."""
        if self.sesion.es_admin or self.ruta_actual.strip("/"):
            return False
        avisos.info(
            self, "Elige una de tus carpetas",
            "En la raíz del almacén solo están tu carpeta personal y la "
            "compartida. Entra en una de ellas para crear carpetas o añadir "
            "archivos."
        )
        return True

    def _es_espacio_base(self, ruta: str) -> bool:
        """Avisa si se intenta renombrar/eliminar la carpeta propia o la común."""
        if not self.sesion.es_espacio_base(ruta):
            return False
        avisos.info(
            self, "Carpeta fija",
            "Tu carpeta personal y la compartida no se pueden renombrar ni "
            "eliminar. Sí puedes trabajar con todo lo que contienen."
        )
        return True

    def _nueva_carpeta(self) -> None:
        if self._en_raiz_sin_permiso():
            return
        nombre = avisos.pedir_texto(self, "Nueva carpeta",
                                    "Nombre de la carpeta")
        if not nombre or not nombre.strip():
            return
        try:
            self.sesion.crear_carpeta(self.ruta_actual, nombre.strip())
        except CustodiaError as exc:
            self._error("No se pudo crear la carpeta", exc)
            return
        self._cargar_arbol()
        self._abrir(self.ruta_actual)
        self._notificar(f"Carpeta «{nombre.strip()}» creada")

    def _subir(self, origenes: list[str] | None = None) -> None:
        """
        Añade uno o varios archivos a la carpeta actual.

        Sin `origenes` pregunta cuáles con el diálogo del sistema; con ellos
        (archivos arrastrados a la ventana) usa esos. La identidad se confirma
        una sola vez para todo el lote.
        """
        if self._en_raiz_sin_permiso():
            return
        if not origenes:
            origenes, _ = QFileDialog.getOpenFileNames(
                self, "Elige los archivos que quieres guardar")
            if not origenes:
                return

        # Subir también es sensible: mete contenido al almacén en tu nombre.
        nombres = (f"«{Path(origenes[0]).name}»" if len(origenes) == 1
                   else f"{len(origenes)} archivos")
        if not self._confirmar_con_codigo(
            "Añadir archivos",
            f"Se añadirá {nombres} a «{self._nombre_carpeta()}». Escribe el "
            "código de tu app de autenticación para confirmarlo.",
            operacion=f"subir: {nombres} a {self.ruta_actual}",
            aceptar="Añadir",
        ):
            return

        fallidos: list[str] = []
        for origen in origenes:
            destino = f"{self.ruta_actual.rstrip('/')}/{Path(origen).name}"
            try:
                self.sesion.escribir(destino, Path(origen).read_bytes())
            except CustodiaError as exc:
                if len(origenes) == 1:
                    self._error("No se pudo guardar el archivo", exc)
                    return
                fallidos.append(Path(origen).name)
            except OSError as exc:
                fallidos.append(f"{Path(origen).name} ({exc.strerror})")
        self._abrir(self.ruta_actual)
        guardados = len(origenes) - len(fallidos)
        if guardados:
            self._notificar(f"«{Path(origenes[0]).name}» añadido" if len(origenes) == 1
                            else f"{guardados} archivos añadidos")
        if fallidos:
            avisos.error(self, "Algunos archivos no se guardaron",
                         "No se pudieron guardar:\n\n" + "\n".join(fallidos))

    def _descargar(self) -> None:
        seleccion = self._seleccion_actual()
        if seleccion is None:
            return
        ruta, es_carpeta = seleccion
        if es_carpeta:
            avisos.info(self, "Elige un archivo",
                        "Solo se pueden guardar copias de archivos.")
            return

        # 1. Límite anti-descarga-masiva.
        bloqueado, restante = self.sesion.estado_descargas()
        if bloqueado:
            avisos.info(
                self, "Descargas bloqueadas",
                "Se alcanzó el límite de descargas. Vuelve a intentarlo en "
                f"{restante // 60 + 1} minutos."
            )
            return

        # 2. Motivo (queda en la bitácora).
        motivo = avisos.pedir_texto(
            self, "Motivo de la descarga", "Motivo",
            descripcion="¿Para qué necesitas esta copia? Queda registrado "
                        "en la bitácora de auditoría."
        )
        if not motivo or not motivo.strip():
            return

        # 3. Re-verificación de identidad antes de exportar.
        if not self._confirmar_con_codigo(
            "Guardar una copia",
            f"Vas a sacar una copia legible de «{Path(ruta).name}» fuera del "
            "almacén. Escribe el código de tu app de autenticación para "
            "confirmarlo.",
            operacion=f"descargar: {ruta}",
            aceptar="Guardar copia",
        ):
            return

        try:
            datos = self.sesion.leer(ruta)
        except CustodiaError as exc:
            self._error("No se pudo leer el archivo", exc)
            return

        destino, _ = QFileDialog.getSaveFileName(self, "Guardar una copia",
                                                 Path(ruta).name)
        if not destino:
            return
        Path(destino).write_bytes(datos)

        bloqueado, restante = self.sesion.registrar_descarga(ruta, motivo.strip())
        self._notificar(f"Copia guardada en «{Path(destino).name}»")
        if bloqueado:
            avisos.info(
                self, "Límite de descargas alcanzado",
                "Esta fue la última descarga permitida por ahora. Las próximas "
                f"quedan bloqueadas unos {restante // 60} minutos."
            )

    def _nombre_carpeta(self) -> str:
        return "Almacén" if self.ruta_actual == "/" else Path(self.ruta_actual).name

    def _renombrar(self) -> None:
        seleccion = self._seleccion_actual()
        if seleccion is None:
            return
        ruta, _ = seleccion
        if self._es_espacio_base(ruta):
            return

        nombre = avisos.pedir_texto(self, "Renombrar", "Nombre nuevo",
                                    valor=Path(ruta).name)
        if not nombre or not nombre.strip() or nombre.strip() == Path(ruta).name:
            return
        if not self._confirmar_con_codigo(
            "Renombrar",
            f"«{Path(ruta).name}» pasará a llamarse «{nombre.strip()}». Escribe "
            "el código de tu app de autenticación para confirmarlo.",
            operacion=f"renombrar: {ruta} -> {nombre.strip()}",
            aceptar="Renombrar",
        ):
            return
        try:
            self.sesion.renombrar(ruta, nombre.strip())
        except CustodiaError as exc:
            self._error("No se pudo renombrar", exc)
            return
        self._cargar_arbol()
        self._abrir(self.ruta_actual)
        self._notificar(f"Ahora se llama «{nombre.strip()}»")

    def _eliminar(self) -> None:
        seleccion = self._seleccion_actual()
        if seleccion is None:
            return
        ruta, es_carpeta = seleccion
        if self._es_espacio_base(ruta):
            return

        # La ventana del código hace también de confirmación: una sola
        # pregunta, en rojo, en lugar de "¿seguro?" y luego el código.
        pregunta = (
            f"Se eliminará «{Path(ruta).name}»"
            + (" y todo lo que contiene" if es_carpeta else "")
            + ". No se puede deshacer. Escribe el código de tu app de "
            "autenticación para confirmarlo."
        )
        if not self._confirmar_con_codigo(
            f"Eliminar «{Path(ruta).name}»", pregunta,
            operacion=f"eliminar: {ruta}", aceptar="Eliminar", peligro=True,
        ):
            return

        try:
            self.sesion.eliminar(ruta, recursivo=es_carpeta)
        except CustodiaError as exc:
            self._error("No se pudo eliminar", exc)
            return
        self._cargar_arbol()
        self._abrir(self.ruta_actual)
        self._notificar(f"«{Path(ruta).name}» eliminado")

    # -- ayudas -------------------------------------------------------------

    def _seleccion_actual(self) -> tuple[str, bool] | None:
        if self._seleccion is None:
            avisos.info(self, "Elige un elemento",
                        "Selecciona primero algo de la lista.")
            return None
        return self._seleccion

    def _error(self, titulo: str, exc: Exception) -> None:
        """
        Los errores explican qué pasó y, cuando los hay, qué hacer.

        Una denegación no es un fallo del programa: es el sistema funcionando.
        El mensaje lo dice así en vez de sonar a avería.
        """
        if isinstance(exc, PermissionDenied):
            detalle = (
                "Windows no autoriza esta operación con tu cuenta. Pídele a un "
                "administrador que te dé el permiso, o revisa el panel de la "
                "derecha para ver qué puedes hacer aquí."
            )
        else:
            detalle = str(exc)
        avisos.error(self, titulo, detalle)

    def _cerrar_sesion(self) -> None:
        """Cierra la ventana pidiendo volver a la pantalla de ingreso."""
        self.cerro_sesion = True
        self.close()

    def closeEvent(self, evento) -> None:
        # El vigilante filtra eventos de toda la aplicación: hay que quitarlo,
        # o seguiría activo (y apuntando a esta ventana) en la sesión siguiente.
        self._vigilante.detener(self._app)
        self._expiracion.stop()
        self._responder_modal(None)
        # Cierra la hoja abierta: revierte, p. ej., un segundo factor activado
        # pero sin confirmar.
        self._cerrar_hoja()
        self.sesion.cerrar()
        super().closeEvent(evento)
