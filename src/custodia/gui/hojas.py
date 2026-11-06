# -*- coding: utf-8 -*-
"""
Hojas de administración: cuentas, bitácora, permisos, segundo factor y clave
de confirmación.

Sustituyen a los antiguos diálogos de widgets. Cada hoja es un panel
QML dentro de la ventana principal (``qml/Hoja*.qml``) y aquí vive su
controlador: la misma lógica que tenían los diálogos —qué se valida, qué se
pide a la sesión, qué se registra—, pero publicando datos para QML en lugar de
llenar widgets.

Los avisos y confirmaciones se piden con `avisos.*(self.v, …)`: al ser `self.v`
la ventana principal, aparecen dentro de ella, encima de la hoja.

Igual que antes, las listas muestran los nombres tal como Windows los
devuelve, incluidas las entradas heredadas y las cuentas desconocidas. Si en la
lista aparece un SID sin nombre es porque esa cuenta se borró, y esconderlo
solo confundiría a quien intente entender por qué alguien tiene o no acceso.
"""
from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import Property, QObject, QTimer, Signal, Slot
from PySide6.QtGui import QGuiApplication

from ..core.acl import Perm
from ..core.errors import AuthenticationError, CustodiaError
from . import avisos

#: Nombres legibles para los tipos de evento que registra la bitácora.
_OPERACIONES = {
    "leer": "Lectura", "escribir": "Escritura", "listar": "Listar carpeta",
    "crear": "Crear", "eliminar": "Eliminar",
    "cambiar_permisos": "Cambio de permisos",
    "descarga": "Descarga", "descarga_masiva": "Descarga masiva (límite)",
    "inicio_sesion": "Inicio de sesión", "cierre_sesion": "Cierre de sesión",
    "bloqueo": "Cuenta bloqueada",
    "bloqueo_pantalla": "Pantalla bloqueada", "desbloqueo": "Desbloqueo",
    "fallo_segundo_factor": "Fallo de segundo factor",
    "segundo_factor_ok": "Segundo factor correcto",
    "segundo_factor_activado": "Segundo factor activado",
    "segundo_factor_desactivado": "Segundo factor desactivado",
    "segundo_factor_restablecido": "Verificación de otra cuenta restablecida",
    "clave_descarga_activada": "Clave de confirmación activada",
    "clave_descarga_desactivada": "Clave de confirmación desactivada",
    "crear_usuario": "Alta de cuenta", "eliminar_usuario": "Baja de cuenta",
    "cambiar_password": "Cambio de contraseña",
    "crear_grupo": "Alta de grupo", "asignar_grupo": "Asignación a grupo",
    "quitar_grupo": "Salida de un grupo", "eliminar_grupo": "Baja de grupo",
    "restablecer_contrasena": "Contraseña restablecida",
    "incorporar_usuario": "Cuenta de Windows añadida",
    "retirar_usuario": "Cuenta retirada de Custodia",
}


def _humano(accion: str) -> str:
    """Nombre legible de una operación; si no se conoce, se formatea el crudo."""
    return _OPERACIONES.get(accion, (accion or "").replace("_", " ").capitalize())


_MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
          "agosto", "septiembre", "octubre", "noviembre", "diciembre"]


def _fecha(momento: str) -> datetime | None:
    try:
        return datetime.fromisoformat((momento or "")[:19])
    except (ValueError, TypeError):
        return None


def _dia(cuando: datetime | None) -> str:
    """Encabezado de sección: «Hoy», «Ayer» o «3 de noviembre de 2026»."""
    if cuando is None:
        return "Sin fecha"
    hoy = datetime.now().date()
    if cuando.date() == hoy:
        return "Hoy"
    if cuando.date() == hoy - timedelta(days=1):
        return "Ayer"
    return f"{cuando.day} de {_MESES[cuando.month - 1]} de {cuando.year}"


def _diferido(metodo):
    """
    Ejecuta el método un ciclo del bucle de eventos más tarde.

    Las acciones que pueden abrir un aviso (que espera respuesta) no deben
    correr dentro del manejador de QML que las llamó: el clic quedaría "a
    medias" mientras el aviso espera. Diferidas, QML termina su manejador
    primero. El resultado se comunica por señales, no por valor de retorno.
    """
    def envoltura(self, *args):
        QTimer.singleShot(0, lambda: metodo(self, *args))
    envoltura.__name__ = metodo.__name__
    envoltura.__doc__ = metodo.__doc__
    return envoltura


class _Controlador(QObject):
    """Base: acceso a la ventana (para avisos) y a la sesión."""

    #: La hoja pide cerrarse (p. ej. tras guardar con éxito).
    cerrar = Signal()

    def __init__(self, ventana) -> None:
        super().__init__(ventana)
        self.v = ventana
        self.sesion = ventana.sesion

    def al_cerrar(self) -> None:
        """Se llama siempre al cerrar la hoja, por el motivo que sea."""


# =============================================================================
#  Cuentas y grupos (RF-01, RF-02)
# =============================================================================

class ControladorCuentas(_Controlador):
    datosChanged = Signal()
    #: La cuenta se creó: QML vacía el formulario.
    cuentaCreada = Signal()

    def __init__(self, ventana) -> None:
        super().__init__(ventana)
        self._cuentas: list[dict] = []
        self._grupos: list[dict] = []
        self.recargar()

    @Property("QVariantList", notify=datosChanged)
    def cuentas(self) -> list:
        return self._cuentas

    @Property("QVariantList", notify=datosChanged)
    def grupos(self) -> list:
        return self._grupos

    @Slot()
    def recargar(self) -> None:
        try:
            cuentas = self.sesion.listar_usuarios()
            grupos = self.sesion.listar_grupos()
        except Exception as exc:
            avisos.error(self.v, "No se pudieron leer las cuentas", str(exc))
            cuentas, grupos = [], []

        self._cuentas = [{
            "usuario": c.username,
            "grupos": list(c.grupos),
            "sid": c.sid,
            "admin": bool(c.es_admin),
            "yo": c.username.lower() == self.sesion.username.lower(),
            "dosPasos": self._dos_pasos(c.username),
            "creada": bool(getattr(c, "creada_por_custodia", True)),
        } for c in cuentas]
        miembros: dict[str, int] = {}
        for c in cuentas:
            for g in c.grupos:
                miembros[g.lower()] = miembros.get(g.lower(), 0) + 1
        internos = {n.lower() for n in self.sesion.grupos_internos()}
        self._grupos = [{
            "nombre": g["name"],
            "descripcion": g.get("description") or "",
            "miembros": miembros.get(g["name"].lower(), 0),
            "interno": g["name"].lower() in internos,
        } for g in grupos]
        self.datosChanged.emit()

    @Property(str, constant=True)
    def grupoApp(self) -> str:
        """El grupo del que no se puede sacar a nadie (todas las cuentas de la app)."""
        return self.sesion.grupos_internos()[0]

    @Slot(str)
    @_diferido
    def quitarDeGrupo(self, usuario: str) -> None:
        cuenta = next((c for c in self._cuentas if c["usuario"] == usuario), None)
        app = self.sesion.grupos_internos()[0].lower()
        grupos = [g for g in (cuenta["grupos"] if cuenta else []) if g.lower() != app]
        if not grupos:
            avisos.info(self.v, "No hay grupos que quitar",
                        f"«{usuario}» solo está en los grupos imprescindibles de "
                        "Custodia, de los que no se puede sacar a nadie.")
            return
        grupo = avisos.pedir_opcion(self.v, "Quitar de un grupo",
                                    f"Grupo del que sacar a {usuario}", grupos)
        if grupo is None:
            return
        if not self.v._confirmar_con_codigo(
            f"Quitar a «{usuario}» de «{grupo}»",
            f"«{usuario}» perderá todo el acceso que le daba «{grupo}». Escribe el "
            "código de tu app de autenticación para confirmarlo.",
            operacion=f"quitar de grupo: {usuario} <- {grupo}",
            aceptar="Quitar del grupo", peligro=True,
        ):
            return
        try:
            self.sesion.quitar_de_grupo(grupo, usuario)
        except Exception as exc:
            avisos.error(self.v, "No se pudo quitar del grupo", str(exc))
            return
        self.recargar()
        self.v._notificar(f"«{usuario}» ya no está en {grupo}")

    @Slot(str)
    @_diferido
    def eliminarGrupo(self, nombre: str) -> None:
        grupo = next((g for g in self._grupos if g["nombre"] == nombre), None)
        if grupo is None or grupo["interno"]:
            return
        n = grupo["miembros"]
        afectados = ("Nadie pertenece a él ahora mismo." if n == 0 else
                     "1 persona perderá el acceso que le daba." if n == 1 else
                     f"{n} personas perderán el acceso que les daba.")
        if not self.v._confirmar_con_codigo(
            f"Eliminar el grupo «{nombre}»",
            f"{afectados} Los permisos concedidos a este grupo dejarán de "
            "funcionar. Escribe el código de tu app de autenticación para "
            "confirmarlo.",
            operacion=f"eliminar grupo: {nombre}",
            aceptar="Eliminar el grupo", peligro=True,
        ):
            return
        try:
            self.sesion.eliminar_grupo(nombre)
        except Exception as exc:
            avisos.error(self.v, "No se pudo eliminar el grupo", str(exc))
            return
        self.recargar()
        self.v._notificar(f"Grupo «{nombre}» eliminado")

    @Slot()
    @_diferido
    def incorporar(self) -> None:
        """Añade a Custodia una cuenta de Windows que ya existía en el equipo."""
        try:
            candidatas = self.sesion.cuentas_incorporables()
        except Exception as exc:
            avisos.error(self.v, "No se pudieron leer las cuentas de Windows", str(exc))
            return
        if not candidatas:
            avisos.info(self.v, "No hay cuentas que añadir",
                        "Todas las cuentas normales de este equipo ya están en "
                        "Custodia. Las cuentas integradas de Windows (Administrador, "
                        "Invitado…) no se pueden usar.")
            return
        usuario = avisos.pedir_opcion(self.v, "Añadir una cuenta de Windows",
                                      "Cuenta de este equipo",
                                      [c["usuario"] for c in candidatas])
        if usuario is None:
            return
        rol = avisos.pedir_opcion(self.v, f"¿Qué será «{usuario}» en Custodia?", "Rol",
                                  ["Usuario", "Administrador de Custodia"])
        if rol is None:
            return
        es_admin = rol.startswith("Administrador")
        if not self.v._confirmar_con_codigo(
            f"Añadir «{usuario}» a Custodia",
            f"«{usuario}» podrá entrar como {rol.lower()} y tendrá su carpeta "
            "personal. Su cuenta de Windows y su contraseña no cambian. Escribe "
            "el código de tu app de autenticación para confirmarlo.",
            operacion=f"incorporar cuenta: {usuario} ({rol.lower()})",
            aceptar="Añadir",
        ):
            return
        try:
            self.sesion.incorporar_usuario(usuario, es_admin=es_admin)
        except Exception as exc:
            avisos.error(self.v, "No se pudo añadir la cuenta", str(exc))
            return
        self.recargar()
        self.v._notificar(f"«{usuario}» ya está en Custodia")

    @Slot(str)
    @_diferido
    def retirar(self, usuario: str) -> None:
        """Saca de Custodia una cuenta incorporada; la de Windows sigue intacta."""
        if not self.v._confirmar_con_codigo(
            f"Retirar a «{usuario}» de Custodia",
            f"«{usuario}» dejará de poder usar Custodia y de ser administrador "
            "aquí. Su cuenta de Windows NO se borra y su carpeta personal se "
            "conserva. Escribe el código de tu app para confirmarlo.",
            operacion=f"retirar cuenta: {usuario}",
            aceptar="Retirar", peligro=True,
        ):
            return
        try:
            self.sesion.retirar_usuario(usuario)
        except Exception as exc:
            avisos.error(self.v, "No se pudo retirar la cuenta", str(exc))
            return
        self.recargar()
        self.v._notificar(f"«{usuario}» ya no está en Custodia")

    def _dos_pasos(self, usuario: str) -> bool:
        try:
            return bool(self.sesion.segundo_factor_de(usuario))
        except Exception:
            return False

    @Slot(str)
    @_diferido
    def restablecerContrasena(self, usuario: str) -> None:
        """
        Para quien olvidó su contraseña: le pone una temporal que solo vale
        para entrar una vez; Windows le obliga a cambiarla al hacerlo.
        """
        aviso_cifrado = ""
        try:
            if self.sesion.pierde_cifrado_al_restablecer(usuario):
                aviso_cifrado = (" Atención: sus archivos cifrados solo para esa "
                                 "persona dejarán de poder abrirse.")
        except Exception:
            pass
        if not self.v._confirmar_con_codigo(
            f"Restablecer la contraseña de «{usuario}»",
            f"Se le pondrá una contraseña temporal y, al entrar con ella, tendrá "
            f"que elegir una nueva.{aviso_cifrado} Escribe el código de tu app "
            "de autenticación para confirmarlo.",
            operacion=f"restablecer contraseña: {usuario}",
            aceptar="Restablecer", peligro=bool(aviso_cifrado),
        ):
            return
        try:
            temporal = self.sesion.restablecer_contrasena(usuario)
        except Exception as exc:
            avisos.error(self.v, "No se pudo restablecer la contraseña", str(exc))
            return
        avisos.mostrar_secreto(
            self.v, f"Contraseña temporal de «{usuario}»",
            "Dásela en persona. Solo sirve para entrar una vez: al hacerlo, "
            "Custodia le pedirá crear la suya. No volverá a mostrarse.",
            temporal,
        )
        del temporal
        self.v._notificar(f"Contraseña de «{usuario}» restablecida")

    @Slot(str)
    @_diferido
    def restablecerDosPasos(self, usuario: str) -> None:
        """Para quien perdió el teléfono: la volverá a configurar con un QR nuevo."""
        if not self.v._confirmar_con_codigo(
            f"Restablecer la verificación de «{usuario}»",
            f"El teléfono que «{usuario}» tiene configurado dejará de servir. "
            "La próxima vez que lo necesite, la app le pedirá configurarla de "
            "nuevo con un QR. Escribe el código de tu app para confirmarlo.",
            operacion=f"restablecer segundo factor: {usuario}",
            aceptar="Restablecer", peligro=True,
        ):
            return
        try:
            self.sesion.restablecer_segundo_factor(usuario)
        except Exception as exc:
            avisos.error(self.v, "No se pudo restablecer", str(exc))
            return
        self.recargar()
        self.v._notificar(f"Verificación de «{usuario}» restablecida")

    @Slot(str, str, bool)
    @_diferido
    def crear(self, usuario: str, password: str, es_admin: bool) -> None:
        usuario = usuario.strip()
        if not usuario or not password:
            avisos.info(self.v, "Faltan datos", "Escribe el usuario y la contraseña.")
            return
        rol = "administradora" if es_admin else "de usuario"
        if not self.v._confirmar_con_codigo(
            "Crear la cuenta",
            f"Se creará en Windows la cuenta {rol} «{usuario}». Escribe el "
            "código de tu app de autenticación para confirmarlo.",
            operacion=f"crear cuenta: {usuario} ({rol})", aceptar="Crear",
        ):
            return
        try:
            self.sesion.crear_usuario(usuario, password, es_admin=es_admin)
        except Exception as exc:
            avisos.error(self.v, "No se pudo crear la cuenta", str(exc))
            return
        self.recargar()
        self.cuentaCreada.emit()
        self.v._notificar(f"Cuenta «{usuario}» creada")

    @Slot(str)
    @_diferido
    def eliminar(self, usuario: str) -> None:
        pregunta = (f"Se eliminará la cuenta de Windows «{usuario}». Su carpeta "
                    "personal se conserva, pero solo los administradores podrán "
                    "abrirla. Escribe el código de tu app de autenticación para "
                    "confirmarlo.")
        if not self.v._confirmar_con_codigo(
            f"Eliminar la cuenta «{usuario}»", pregunta,
            operacion=f"eliminar cuenta: {usuario}",
            aceptar="Eliminar la cuenta", peligro=True,
        ):
            return
        try:
            self.sesion.eliminar_usuario(usuario)
        except Exception as exc:
            avisos.error(self.v, "No se pudo eliminar", str(exc))
            return
        self.recargar()
        self.v._notificar(f"Cuenta «{usuario}» eliminada")

    @Slot()
    @_diferido
    def crearGrupo(self) -> None:
        nombre = avisos.pedir_texto(self.v, "Grupo nuevo", "Nombre del grupo")
        if not nombre or not nombre.strip():
            return
        try:
            self.sesion.crear_grupo(nombre.strip())
        except Exception as exc:
            avisos.error(self.v, "No se pudo crear el grupo", str(exc))
            return
        self.recargar()
        self.v._notificar(f"Grupo «{nombre.strip()}» creado")

    @Slot(str)
    @_diferido
    def asignar(self, usuario: str) -> None:
        grupos = [g["nombre"] for g in self._grupos]
        grupo = avisos.pedir_opcion(self.v, "Asignar a un grupo",
                                    f"Grupo para {usuario}", grupos)
        if grupo is None:
            return
        if not self.v._confirmar_con_codigo(
            "Asignar a un grupo",
            f"«{usuario}» pasará a formar parte de «{grupo}» y tendrá sus "
            "permisos. Escribe el código de tu app de autenticación para "
            "confirmarlo.",
            operacion=f"asignar grupo: {usuario} -> {grupo}", aceptar="Asignar",
        ):
            return
        try:
            self.sesion.asignar_a_grupo(grupo, usuario)
        except Exception as exc:
            avisos.error(self.v, "No se pudo asignar", str(exc))
            return
        self.recargar()
        self.v._notificar(f"«{usuario}» ahora está en {grupo}")


# =============================================================================
#  Bitácora de auditoría (RF-05)
# =============================================================================

class ControladorBitacora(_Controlador):
    """
    Visor de solo lectura. No hay forma de editar ni borrar registros desde
    aquí: la integridad de la bitácora se conserva. Los datos que se muestran
    son exactamente los que almacena `audit`.
    """

    datosChanged = Signal()
    visiblesChanged = Signal()

    def __init__(self, ventana) -> None:
        super().__init__(ventana)
        self._eventos: list[dict] = []
        self._visibles: list[dict] = []
        self._usuarios: list[str] = []
        self._operaciones: list[dict] = []
        self._dias: list[str] = []
        self._filtros = ("", "", "", "", "", 0)
        self.recargar()

    @Property("QVariantList", notify=visiblesChanged)
    def eventos(self) -> list:
        return self._visibles

    @Property(int, notify=datosChanged)
    def total(self) -> int:
        return len(self._eventos)

    @Property(int, notify=datosChanged)
    def denegados(self) -> int:
        return sum(1 for e in self._eventos if not e["exito"])

    @Property("QVariantList", notify=datosChanged)
    def usuarios(self) -> list:
        return self._usuarios

    @Property("QVariantList", notify=datosChanged)
    def operaciones(self) -> list:
        return self._operaciones

    @Property("QVariantList", notify=datosChanged)
    def diasConEventos(self) -> list:
        """Días (AAAA-MM-DD) con algún evento: el calendario los marca."""
        return self._dias

    @Slot()
    def recargar(self) -> None:
        try:
            crudos = self.sesion.bitacora(solo_denegados=False, limite=1000)
        except Exception as exc:
            avisos.error(self.v, "No se pudo leer la bitácora", str(exc))
            crudos = []

        self._eventos = []
        for e in crudos:
            cuando = _fecha(e["momento"])
            self._eventos.append({
                "momento": e["momento"] or "",
                "cuando": cuando,
                "dia": _dia(cuando),
                "hora": cuando.strftime("%H:%M") if cuando else "",
                "largo": (f"{cuando.day} de {_MESES[cuando.month - 1]} de "
                          f"{cuando.year}, a las {cuando.strftime('%H:%M:%S')}"
                          if cuando else (e["momento"] or "—")),
                "usuario": e["usuario"] or "",
                "accion": e["accion"] or "",
                "operacion": _humano(e["accion"]),
                "ruta": e["ruta"] or "",
                "exito": bool(e["exito"]),
                "detalle": e["detalle"] or "",
            })
        self._usuarios = sorted({e["usuario"] for e in self._eventos if e["usuario"]})
        acciones = sorted({e["accion"] for e in self._eventos if e["accion"]},
                          key=_humano)
        self._operaciones = [{"clave": a, "nombre": _humano(a)} for a in acciones]
        self._dias = sorted({e["cuando"].date().isoformat()
                             for e in self._eventos if e["cuando"] is not None})
        self.datosChanged.emit()
        self.filtrar(*self._filtros)

    @Slot(str, str, str, str, str, int)
    def filtrar(self, texto: str, usuario: str, operacion: str,
                desde: str, hasta: str, resultado: int) -> None:
        """
        desde / hasta: días AAAA-MM-DD, ambos incluidos ("" = sin límite).
        resultado: 0 todos, 1 solo denegados, 2 solo permitidos.
        """
        self._filtros = (texto, usuario, operacion, desde, hasta, resultado)
        texto = texto.strip().lower()
        try:
            dia_desde = datetime.fromisoformat(desde).date() if desde else None
            dia_hasta = datetime.fromisoformat(hasta).date() if hasta else None
        except ValueError:
            dia_desde = dia_hasta = None
        if dia_desde and dia_hasta and dia_desde > dia_hasta:
            dia_desde, dia_hasta = dia_hasta, dia_desde

        visibles = []
        for e in self._eventos:
            if usuario and e["usuario"] != usuario:
                continue
            if operacion and e["accion"] != operacion:
                continue
            if resultado == 1 and e["exito"]:
                continue
            if resultado == 2 and not e["exito"]:
                continue
            if (dia_desde or dia_hasta) and e["cuando"] is None:
                continue
            if dia_desde and e["cuando"].date() < dia_desde:
                continue
            if dia_hasta and e["cuando"].date() > dia_hasta:
                continue
            if texto:
                aguja = " ".join([e["usuario"], e["ruta"], e["detalle"],
                                  e["operacion"]]).lower()
                if texto not in aguja:
                    continue
            visibles.append({k: v for k, v in e.items() if k != "cuando"})
        self._visibles = visibles
        self.visiblesChanged.emit()


# =============================================================================
#  Permisos de un elemento (RF-06)
# =============================================================================

#: Permisos que se ofrecen al conceder, con el nombre que ve la persona.
_OFRECIDOS = [
    ("Abrir y leer", Perm.LEER),
    ("Modificar", Perm.ESCRIBIR),
    ("Entrar y recorrer", Perm.EJECUTAR),
    ("Eliminar", Perm.ELIMINAR),
    ("Control total", Perm.TOTAL),
]

_NOMBRE_PERMISO = {"LEER": "Leer", "ESCRIBIR": "Modificar", "EJECUTAR": "Recorrer",
                   "ELIMINAR": "Eliminar", "LISTAR": "Listar", "TOTAL": "Control total"}


class ControladorPermisos(_Controlador):
    """
    Edita la DACL bajo suplantación, así que quien decide si esta persona
    puede cambiar estos permisos es el kernel: hace falta el derecho
    WRITE_DAC, que tienen los administradores y el propietario del objeto.
    """

    datosChanged = Signal()
    #: El permiso se concedió: QML vacía el formulario.
    concedido = Signal()

    def __init__(self, ventana, ruta: str) -> None:
        super().__init__(ventana)
        self.ruta = ruta
        self._crudas: list = []
        self._entradas: list[dict] = []
        self._principales: list[str] = []
        self._cargar_principales()
        self.recargar()

    @Property(str, constant=True)
    def nombre(self) -> str:
        return "Almacén" if self.ruta == "/" else self.ruta.rstrip("/").split("/")[-1]

    @Property(str, constant=True)
    def rutaCompleta(self) -> str:
        return self.ruta

    @Property("QVariantList", notify=datosChanged)
    def entradas(self) -> list:
        return self._entradas

    @Property("QVariantList", constant=True)
    def principales(self) -> list:
        return self._principales

    @Property("QVariantList", constant=True)
    def ofrecidos(self) -> list:
        return [n for n, _ in _OFRECIDOS]

    def _cargar_principales(self) -> None:
        try:
            nombres = [c.username for c in self.sesion.listar_usuarios()]
            nombres += [g["name"] for g in self.sesion.listar_grupos()]
        except CustodiaError:
            nombres = []
        self._principales = nombres

    @Slot()
    def recargar(self) -> None:
        try:
            self._crudas = self.sesion.entradas_de_permisos(self.ruta)
        except CustodiaError as exc:
            avisos.error(self.v, "No se pudieron leer los permisos", str(exc))
            self._crudas = []
        self._entradas = [{
            "principal": e.principal,
            "corto": e.principal.split("\\")[-1],
            "permitir": bool(e.permitir),
            "permisos": [_NOMBRE_PERMISO.get(p, p.capitalize()) for p in e.permisos],
            "heredado": bool(e.heredado),
            "propagado": bool(e.hereda_a_hijos),
        } for e in self._crudas]
        self.datosChanged.emit()

    def _propias(self) -> list[tuple[str, int, bool, bool]]:
        """
        Las entradas que se pueden reescribir. Las heredadas se omiten a
        propósito: Windows las regenera desde la carpeta padre. Incluirlas las
        convertiría en entradas propias, y a partir de ahí dejarían de
        actualizarse cuando cambie el origen.
        """
        return [(e.sid, e.mascara, e.permitir, e.hereda_a_hijos)
                for e in self._crudas if not e.heredado]

    @Slot(str, "QVariantList", bool)
    @_diferido
    def conceder(self, principal: str, marcados: list, hereda: bool) -> None:
        principal = principal.strip()
        if not principal:
            avisos.info(self.v, "Falta la cuenta",
                        "Elige o escribe a quién le das el permiso.")
            return
        mascara = 0
        for (_, permiso), marcado in zip(_OFRECIDOS, marcados):
            if marcado:
                mascara |= int(permiso)
        if not mascara:
            avisos.info(self.v, "Falta el permiso", "Marca al menos un permiso.")
            return
        que = ", ".join(n.lower() for (n, _), m in zip(_OFRECIDOS, marcados) if m)
        if not self.v._confirmar_con_codigo(
            "Conceder un permiso",
            f"«{principal}» podrá {que} en «{self.nombre}». Escribe el código de "
            "tu app de autenticación para confirmarlo.",
            operacion=f"conceder permiso: {principal} en {self.ruta} ({que})",
            aceptar="Conceder",
        ):
            return
        entradas = self._propias()
        entradas.append((principal, mascara, True, hereda))
        if self._escribir(entradas):
            self.concedido.emit()
            self.v._notificar(f"Permiso concedido a «{principal}»")

    @Slot(int)
    @_diferido
    def quitar(self, indice: int) -> None:
        if not 0 <= indice < len(self._crudas):
            return
        entrada = self._crudas[indice]
        if entrada.heredado:
            avisos.info(
                self.v, "Entrada heredada",
                "Esta entrada viene de la carpeta que la contiene. Cámbiala "
                "allí, o rompe la herencia de este elemento."
            )
            return
        nombre = entrada.principal.split("\\")[-1]
        if not self.v._confirmar_con_codigo(
                f"Quitar el permiso de «{nombre}»",
                f"«{nombre}» dejará de tener esta entrada en «{self.nombre}». "
                "Escribe el código de tu app de autenticación para confirmarlo.",
                operacion=f"quitar permiso: {entrada.principal} en {self.ruta}",
                aceptar="Quitar", peligro=True):
            return
        entradas = [e for e in self._propias() if e[0] != entrada.sid]
        if self._escribir(entradas):
            self.v._notificar(f"Permiso de «{nombre}» quitado")

    def _escribir(self, entradas) -> bool:
        try:
            self.sesion.escribir_permisos(self.ruta, entradas)
        except Exception as exc:
            avisos.error(
                self.v, "No se pudieron cambiar los permisos",
                "Windows no autoriza este cambio con tu cuenta. Para cambiar "
                "permisos hace falta ser administrador o dueño del elemento.\n\n"
                f"{exc}"
            )
            return False
        self.recargar()
        return True


# =============================================================================
#  Verificación en dos pasos
# =============================================================================

class ControladorContrasena(_Controlador):
    """
    Cambiar la propia contraseña. Exige la actual (como Windows con
    Ctrl+Alt+Supr): un fallo cuenta para el bloqueo de la cuenta, así que una
    sesión abierta y desatendida no sirve para quedarse con la cuenta.
    """

    @Slot(str, str, str, result=str)
    def cambiar(self, actual: str, nueva: str, repetida: str) -> str:
        """Devuelve un mensaje de error, o "" si se cambió."""
        if not actual:
            return "Escribe tu contraseña actual."
        if nueva != repetida:
            return "Las dos contraseñas nuevas no coinciden."
        try:
            self.sesion.cambiar_mi_contrasena(actual, nueva)
        except AuthenticationError as exc:
            if self.sesion.cuenta_bloqueada():
                QTimer.singleShot(0, self.v._cerrar_sesion)
            return str(exc)
        except CustodiaError as exc:
            return str(exc)
        self.v._notificar("Contraseña cambiada")
        self.cerrar.emit()
        return ""


def _qr_data_url(texto: str, escala: int = 8, margen: int = 4) -> str:
    """
    Dibuja el QR de `texto` y lo devuelve como data URL PNG para QML.

    Se genera aquí, en el equipo: el enlace lleva el secreto del segundo
    factor y no debe pasar por ningún servicio externo de códigos QR. Módulos
    negros sobre blanco con margen de 4 módulos, que es lo que las cámaras
    leen mejor (también en el tema oscuro).
    """
    import base64

    import segno
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRect
    from PySide6.QtGui import QColor, QImage, QPainter

    try:
        matriz = [list(fila) for fila in segno.make(texto, error="m").matrix]
    except Exception:
        return ""
    lado = (len(matriz) + 2 * margen) * escala
    imagen = QImage(lado, lado, QImage.Format.Format_RGB32)
    imagen.fill(QColor("white"))
    pintor = QPainter(imagen)
    negro = QColor("#0B0D12")
    for y, fila in enumerate(matriz):
        for x, modulo in enumerate(fila):
            if modulo:
                pintor.fillRect(QRect((x + margen) * escala, (y + margen) * escala,
                                      escala, escala), negro)
    pintor.end()

    datos = QByteArray()
    buf = QBuffer(datos)
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    imagen.save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(bytes(datos)).decode()


class ControladorSegundoFactor(_Controlador):
    """
    Al activarlo se genera el secreto y se pide un código de confirmación antes
    de dejarlo en firme: así nadie se queda bloqueado fuera por haber activado
    un secreto que su app de autenticación nunca llegó a guardar.
    """

    estadoChanged = Signal()
    error = Signal(str)

    def __init__(self, ventana) -> None:
        super().__init__(ventana)
        self._pendiente = False
        self._secreto = ""
        self._qr = ""
        self._estado = "activo" if self.sesion.segundo_factor_activo() else "inactivo"

    @Property(str, notify=estadoChanged)
    def qr(self) -> str:
        """El QR del enlace otpauth como data URL (vacío si no hay)."""
        return self._qr

    @Property(str, notify=estadoChanged)
    def estado(self) -> str:
        return self._estado

    @Property(str, notify=estadoChanged)
    def secreto(self) -> str:
        # Agrupado de 4 en 4: se copia a mano sin perderse.
        return " ".join(self._secreto[i:i + 4] for i in range(0, len(self._secreto), 4))

    def _poner(self, estado: str) -> None:
        self._estado = estado
        self.estadoChanged.emit()

    @Slot()
    def activar(self) -> None:
        self._secreto, uri = self.sesion.activar_segundo_factor()
        self._qr = _qr_data_url(uri)
        self._pendiente = True
        self._poner("configurar")

    @Slot()
    def copiar(self) -> None:
        """
        Copia la clave al portapapeles y la borra de ahí al minuto, para que
        no se quede a la vista de cualquier otra aplicación.
        """
        portapapeles = QGuiApplication.clipboard()
        portapapeles.setText(self._secreto)
        copiado = self._secreto

        def limpiar() -> None:
            if portapapeles.text() == copiado:
                portapapeles.clear()

        QTimer.singleShot(60_000, limpiar)
        self.v._notificar("Clave copiada; se borrará del portapapeles en un minuto")

    @Slot(str)
    def confirmar(self, codigo: str) -> None:
        if self.sesion.verificar_segundo_factor(codigo.strip()):
            self._pendiente = False
            self._secreto = ""
            self._qr = ""
            self._poner("activo")
            self.v._notificar("Verificación en dos pasos activada")
        else:
            self.error.emit("El código no coincide. Revisa que la hora de tu "
                            "teléfono esté en automático y vuelve a intentarlo.")

    @Slot()
    @_diferido
    def desactivar(self) -> None:
        # Pedir el código impide que alguien con la sesión abierta la quite
        # para saltarse la verificación en las demás operaciones.
        if not self.v._confirmar_con_codigo(
            "Desactivar la verificación en dos pasos",
            "Tu cuenta volverá a entrar solo con la contraseña, y no podrás "
            "eliminar, descargar ni cambiar permisos hasta activarla de nuevo. "
            "Escribe el código de tu app para confirmarlo.",
            operacion="desactivar segundo factor",
            aceptar="Desactivar", peligro=True,
        ):
            return
        self.sesion.desactivar_segundo_factor()
        self._poner("inactivo")
        self.v._notificar("Verificación en dos pasos desactivada")

    def al_cerrar(self) -> None:
        # Si se activó pero no se confirmó, se revierte: no dejamos la cuenta
        # con un secreto que la app de autenticación quizá no guardó.
        if self._pendiente:
            self.sesion.desactivar_segundo_factor()
            self._pendiente = False
        self._secreto = ""
        self._qr = ""
