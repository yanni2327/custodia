# -*- coding: utf-8 -*-
"""
Cuentas y grupos locales de Windows.

Los usuarios de esta aplicación son cuentas reales de Windows. Puedes verlas en
``lusrmgr.msc`` o con ``net user``. No hay tabla de usuarios en ninguna base de
datos: la SAM de Windows es la base de datos.

------------------------------------------------------------------------------
SALVAGUARDA
------------------------------------------------------------------------------
Estamos creando y borrando cuentas reales del sistema operativo con privilegios
administrativos. Un error aquí no corrompe una fila: deja la máquina inservible.

Por eso toda cuenta creada por la aplicación entra al grupo ``APP_GROUP``, y
:func:`_assert_gestionable` se ejecuta ANTES de cualquier modificación o borrado.
Si la cuenta no pertenece a ese grupo, la operación se rechaza. Ese es el motivo
de que un bug no pueda borrar al Administrador ni una cuenta del sistema.
"""
from __future__ import annotations

from dataclasses import dataclass

import win32api
import win32net
import win32netcon
import win32security
import pywintypes

from . import config
from .errors import AccountError, ProtectedAccount

_ERROR_ACCESS_DENIED = 5
_NERR_UserNotFound = 2221
_NERR_UserExists = 2224
_NERR_PasswordTooShort = 2245  # también: no cumple la política de complejidad

#: Códigos de "el grupo ya existe" y "el grupo no existe".
#:
#: Ojo con esto: las APIs de grupo LOCAL devuelven los códigos de la familia
#: ERROR_*_ALIAS (1376-1379), no los NERR_Group* (2220-2223) que uno esperaría
#: por el nombre de la función. Los NERR_Group* corresponden a los grupos
#: GLOBALES de un dominio, que no es lo que usamos aquí. Se aceptan ambos por
#: seguridad.
_GRUPO_YA_EXISTE = (1379, 2223)      # ERROR_ALIAS_EXISTS, NERR_GroupExists
_GRUPO_NO_EXISTE = (1376, 2220)      # ERROR_NO_SUCH_ALIAS, NERR_GroupNotFound
_YA_ES_MIEMBRO = (1378,)             # ERROR_MEMBER_IN_ALIAS
_NO_ES_MIEMBRO = (1377,)             # ERROR_MEMBER_NOT_IN_ALIAS


@dataclass
class CuentaInfo:
    """Datos públicos de una cuenta. Nunca incluye nada sensible."""

    username: str
    display_name: str
    sid: str
    grupos: list[str]
    es_admin: bool
    #: True si la creó Custodia; False si era una cuenta de Windows que ya
    #: existía y se incorporó (p. ej. la cuenta personal del dueño del equipo).
    #: Las incorporadas nunca se borran desde aquí, solo se retiran.
    creada_por_custodia: bool = True


# ---------------------------------------------------------------------------
# Utilidades internas
# ---------------------------------------------------------------------------

def _host() -> str:
    """Nombre de esta máquina, necesario para calificar los nombres de cuenta."""
    return win32api.GetComputerName()


def _calificado(username: str) -> str:
    """``usuario`` -> ``MAQUINA\\usuario``, formato que exigen las APIs de grupo."""
    return f"{_host()}\\{username}"


def sid_de(nombre: str) -> str:
    """Devuelve el SID en texto de un usuario o grupo local."""
    try:
        sid, _, _ = win32security.LookupAccountName(None, nombre)
        return win32security.ConvertSidToStringSid(sid)
    except pywintypes.error as exc:
        raise AccountError(f"No se encontró la cuenta '{nombre}'") from exc


def _grupos_de(username: str) -> list[str]:
    try:
        return list(win32net.NetUserGetLocalGroups(config.SERVER, username))
    except pywintypes.error as exc:
        if exc.winerror == _NERR_UserNotFound:
            raise AccountError(f"El usuario '{username}' no existe") from exc
        raise AccountError(f"No se pudieron leer los grupos: {exc.strerror}") from exc


#: Cuentas integradas de Windows que la aplicación nunca toca ni ofrece.
_CUENTAS_SISTEMA = {"administrator", "administrador", "guest", "invitado",
                    "system", "defaultaccount", "wdagutilityaccount"}

#: Las cuentas integradas también se reconocen por el final de su SID (RID),
#: que no cambia con el idioma ni si alguien las renombra: 500 Administrador,
#: 501 Invitado, 503 DefaultAccount, 504 WDAGUtilityAccount.
_RID_SISTEMA = {"500", "501", "503", "504"}

#: Marca que llevan en el comentario las cuentas que crea Custodia.
_MARCA_CUSTODIA = "Custodia:"


def _es_cuenta_del_sistema(username: str) -> bool:
    if username.lower() in _CUENTAS_SISTEMA:
        return True
    try:
        return sid_de(username).rsplit("-", 1)[-1] in _RID_SISTEMA
    except AccountError:
        return False


def _assert_gestionable(username: str) -> None:
    """
    Rechaza cualquier cuenta que no haya creado esta aplicación.

    Se llama al principio de TODA función que modifique o elimine una cuenta.
    """
    if username.lower() in _CUENTAS_SISTEMA:
        raise ProtectedAccount(
            f"'{username}' es una cuenta del sistema y no se puede administrar "
            "desde esta aplicación"
        )

    if config.APP_GROUP not in _grupos_de(username):
        raise ProtectedAccount(
            f"'{username}' no pertenece al grupo '{config.APP_GROUP}', así que no "
            "fue creada por esta aplicación y no se va a tocar"
        )


# ---------------------------------------------------------------------------
# Preparación
# ---------------------------------------------------------------------------

def asegurar_grupos() -> None:
    """
    Crea los grupos locales de la aplicación si no existen. Idempotente.

    Ejecutar una vez al arrancar el servicio.
    """
    for nombre, comentario in (
        (config.APP_GROUP, "Cuentas administradas por Custodia"),
        (config.ADMIN_GROUP, "Administradores de la aplicación Custodia"),
    ):
        try:
            win32net.NetLocalGroupAdd(config.SERVER, 1, {
                "name": nombre,
                "comment": comentario,
            })
        except pywintypes.error as exc:
            if exc.winerror in _GRUPO_YA_EXISTE:
                continue
            if exc.winerror == _ERROR_ACCESS_DENIED:
                raise AccountError(
                    "Se requieren privilegios de administrador para crear los "
                    "grupos locales. Ejecuta el servicio como administrador."
                ) from exc
            raise AccountError(f"No se pudo crear el grupo '{nombre}': {exc.strerror}") from exc


# ---------------------------------------------------------------------------
# Usuarios
# ---------------------------------------------------------------------------

def crear_usuario(username: str, password: str, display_name: str = "",
                  es_admin: bool = False) -> CuentaInfo:
    """
    Crea una cuenta local real de Windows y la mete en los grupos de la app.

    La contraseña la valida Windows contra la política de la máquina: si es
    demasiado corta o no cumple la complejidad exigida, la creación falla. No
    replicamos esa política en nuestro código; dejamos que la imponga el sistema.
    """
    nombre = f"{config.USER_PREFIX}{username}"

    if len(nombre) > 20:
        raise AccountError(
            "Los nombres de cuenta local de Windows no pueden pasar de 20 caracteres"
        )

    try:
        win32net.NetUserAdd(config.SERVER, 1, {
            "name": nombre,
            "password": password,
            "priv": win32netcon.USER_PRIV_USER,     # usuario normal, no admin
            "home_dir": None,
            # La marca va SIEMPRE, también con nombre descriptivo: es lo que
            # distingue una cuenta creada aquí (se puede borrar) de una cuenta
            # de Windows incorporada (solo se retira).
            "comment": f"{_MARCA_CUSTODIA} {display_name or username}",
            "flags": win32netcon.UF_SCRIPT | win32netcon.UF_DONT_EXPIRE_PASSWD,
            "script_path": None,
        })
    except pywintypes.error as exc:
        if exc.winerror == _NERR_UserExists:
            raise AccountError(f"El usuario '{nombre}' ya existe") from exc
        if exc.winerror == _NERR_PasswordTooShort:
            raise AccountError(
                "La contraseña no cumple la política de seguridad de Windows "
                "(longitud o complejidad insuficiente)"
            ) from exc
        if exc.winerror == _ERROR_ACCESS_DENIED:
            raise AccountError(
                "Se requieren privilegios de administrador para crear cuentas"
            ) from exc
        raise AccountError(f"No se pudo crear la cuenta: {exc.strerror}") from exc

    # A partir de aquí la cuenta ya existe. Si algo falla al añadirla a los
    # grupos, la borramos para no dejar una cuenta huérfana que ninguna
    # salvaguarda reconocería después como propia.
    try:
        _añadir_a_grupo(config.APP_GROUP, nombre)
        if es_admin:
            _añadir_a_grupo(config.ADMIN_GROUP, nombre)
    except Exception:
        try:
            win32net.NetUserDel(config.SERVER, nombre)
        except Exception:
            pass
        raise

    # El espacio personal se crea aquí para que una cuenta nueva sea
    # utilizable de inmediato. Import local: `espacios` usa `acl`, que no
    # necesita conocer este módulo, y hacerlo arriba crearía un ciclo.
    try:
        from . import espacios
        espacios.asegurar_espacio(nombre)
    except Exception:
        # La cuenta ya existe y es válida; sin su carpeta seguirá pudiendo
        # entrar, así que esto no debe deshacer la creación.
        pass

    return info_usuario(nombre)


def eliminar_usuario(username: str) -> None:
    """
    Elimina una cuenta creada por la aplicación.

    Solo las que creó Custodia: una cuenta de Windows que ya existía y se
    incorporó (la personal del dueño del equipo, por ejemplo) se retira con
    :func:`retirar_de_custodia`, nunca se borra desde aquí.
    """
    _assert_gestionable(username)
    if not info_usuario(username).creada_por_custodia:
        raise ProtectedAccount(
            f"'{username}' es una cuenta de Windows que ya existía antes de "
            "Custodia. No se borra desde aquí: retírala de Custodia y la cuenta "
            "de Windows seguirá intacta."
        )
    try:
        win32net.NetUserDel(config.SERVER, username)
    except pywintypes.error as exc:
        if exc.winerror == _NERR_UserNotFound:
            raise AccountError(f"El usuario '{username}' no existe") from exc
        raise AccountError(f"No se pudo eliminar la cuenta: {exc.strerror}") from exc


def cambiar_password(username: str, nueva: str) -> None:
    """Cambia la contraseña de una cuenta de la aplicación (acción de admin)."""
    _assert_gestionable(username)
    try:
        # Nivel 1003 = solo el campo de contraseña.
        win32net.NetUserSetInfo(config.SERVER, username, 1003, {"password": nueva})
    except pywintypes.error as exc:
        if exc.winerror == _NERR_PasswordTooShort:
            raise AccountError(
                "La contraseña no cumple la política de seguridad de Windows"
            ) from exc
        raise AccountError(f"No se pudo cambiar la contraseña: {exc.strerror}") from exc


#: Letras y números sin los que se confunden al dictarlos o copiarlos a mano
#: (0/O, 1/l/I).
_ALFABETO_TEMPORAL = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnpqrstuvwxyz23456789"


def contrasena_temporal() -> str:
    """
    Contraseña temporal aleatoria, en tres bloques fáciles de dictar
    (p. ej. ``Kp7x-mR4q-Wn9c``).

    12 caracteres de 56 posibles (~70 bits) más los guiones: de sobra para
    algo que solo vale hasta el primer inicio de sesión. Siempre lleva
    mayúscula, minúscula, número y símbolo, para cumplir también una política
    de complejidad de Windows si el equipo la tiene.
    """
    import secrets
    import string

    while True:
        bloques = ["".join(secrets.choice(_ALFABETO_TEMPORAL) for _ in range(4))
                   for _ in range(3)]
        texto = "".join(bloques)
        if (any(c in string.ascii_uppercase for c in texto)
                and any(c in string.ascii_lowercase for c in texto)
                and any(c.isdigit() for c in texto)):
            return "-".join(bloques)


def regla_contrasena(nueva: str) -> str | None:
    """
    Regla mínima de Custodia para una contraseña nueva; None si la cumple.

    Existe porque Windows solo exige lo que diga la política del equipo, y en
    un equipo doméstico esa política suele no exigir nada (acepta «abc»).
    Windows sigue aplicando la suya encima de esta.
    """
    if len(nueva) < 8:
        return "Usa al menos 8 caracteres."
    if not any(c.isalpha() for c in nueva) or not any(c.isdigit() for c in nueva):
        return "Combina letras y números."
    return None


def forzar_cambio_de_contrasena(username: str) -> None:
    """
    Marca la cuenta para que Windows exija cambiar la contraseña en el próximo
    inicio de sesión (lo mismo que la casilla de «Usuarios y grupos locales»).
    Hasta que la cambie, `LogonUser` devuelve el error 1907.
    """
    _assert_gestionable(username)
    try:
        datos = win32net.NetUserGetInfo(config.SERVER, username, 3)
        datos["password_expired"] = 1
        datos["password"] = None          # no tocar la contraseña aquí
        # Con «la contraseña nunca expira» Windows ignora la marca de cambio
        # obligatorio (su propia consola tampoco deja tener las dos). Se quita
        # aquí; `cambiar_password_propia` la repone en las cuentas creadas por
        # Custodia en cuanto la persona elige su contraseña nueva.
        datos["flags"] &= ~win32netcon.UF_DONT_EXPIRE_PASSWD
        win32net.NetUserSetInfo(config.SERVER, username, 3, datos)
    except pywintypes.error as exc:
        raise AccountError(
            f"No se pudo marcar el cambio de contraseña: {exc.strerror}"
        ) from exc


def cambiar_password_propia(username: str, actual: str, nueva: str) -> None:
    """
    Cambia la contraseña conociendo la actual (o la temporal), como hace
    Windows con Ctrl+Alt+Supr. Funciona también si la cuenta está marcada
    para cambiarla, y al hacerlo se quita la marca.

    :raises AuthenticationError: la contraseña actual no es correcta.
    :raises AccountError: la nueva no cumple la política de Windows.
    """
    from .errors import AuthenticationError

    try:
        win32net.NetUserChangePassword(config.SERVER, username, actual, nueva)
    except pywintypes.error as exc:
        if exc.winerror == 86:                       # ERROR_INVALID_PASSWORD
            raise AuthenticationError("La contraseña actual no es correcta.") from exc
        if exc.winerror == _NERR_PasswordTooShort:
            raise AccountError(
                "Windows no acepta esa contraseña: no cumple la política de "
                "seguridad del equipo (longitud, complejidad o historial)."
            ) from exc
        raise AccountError(f"No se pudo cambiar la contraseña: {exc.strerror}") from exc

    # Las cuentas que crea Custodia llevan «la contraseña nunca expira»; si se
    # quitó para forzar el cambio, se repone ahora que ya tiene la suya.
    try:
        if info_usuario(username).creada_por_custodia:
            flags = win32net.NetUserGetInfo(config.SERVER, username, 1)["flags"]
            if not flags & win32netcon.UF_DONT_EXPIRE_PASSWD:
                win32net.NetUserSetInfo(config.SERVER, username, 1008, {
                    "flags": flags | win32netcon.UF_DONT_EXPIRE_PASSWD,
                })
    except (pywintypes.error, AccountError):
        pass   # la contraseña ya cambió; esto es secundario


def info_usuario(username: str) -> CuentaInfo:
    """Datos públicos de una cuenta."""
    try:
        datos = win32net.NetUserGetInfo(config.SERVER, username, 2)
    except pywintypes.error as exc:
        if exc.winerror == _NERR_UserNotFound:
            raise AccountError(f"El usuario '{username}' no existe") from exc
        raise AccountError(f"No se pudo leer la cuenta: {exc.strerror}") from exc

    grupos = _grupos_de(username)
    return CuentaInfo(
        username=username,
        display_name=datos.get("full_name") or datos.get("comment") or username,
        sid=sid_de(username),
        grupos=grupos,
        es_admin=config.ADMIN_GROUP in grupos,
        creada_por_custodia=(datos.get("comment") or "").startswith(_MARCA_CUSTODIA),
    )


def cuentas_incorporables() -> list[dict]:
    """
    Cuentas de Windows de este equipo que podrían incorporarse a Custodia.

    Solo cuentas normales y habilitadas que todavía no son de la aplicación;
    nunca las integradas del sistema (Administrador, Invitado…).
    """
    try:
        miembros, _, _ = win32net.NetLocalGroupGetMembers(config.SERVER, config.APP_GROUP, 1)
        ya_dentro = {m["name"].split("\\")[-1].lower() for m in miembros}
    except pywintypes.error:
        ya_dentro = set()

    salida, reanudar = [], 0
    while True:
        try:
            lote, _, reanudar = win32net.NetUserEnum(
                config.SERVER, 1, win32netcon.FILTER_NORMAL_ACCOUNT, reanudar)
        except pywintypes.error as exc:
            raise AccountError(f"No se pudieron listar las cuentas: {exc.strerror}") from exc
        for u in lote:
            nombre = u["name"]
            if (nombre.lower() in ya_dentro
                    or u.get("flags", 0) & win32netcon.UF_ACCOUNTDISABLE
                    or _es_cuenta_del_sistema(nombre)):
                continue
            salida.append({"usuario": nombre, "descripcion": u.get("comment") or ""})
        if not reanudar:
            break
    return sorted(salida, key=lambda c: c["usuario"].lower())


def incorporar_usuario(username: str, es_admin: bool = False) -> CuentaInfo:
    """
    Da de alta en Custodia una cuenta de Windows que ya existía.

    No cambia nada de la cuenta en sí (ni contraseña ni privilegios de
    Windows): solo la mete en los grupos de la aplicación y le prepara su
    carpeta personal.
    """
    if _es_cuenta_del_sistema(username):
        raise ProtectedAccount(
            f"'{username}' es una cuenta integrada de Windows y no se puede "
            "usar en Custodia"
        )
    info_usuario(username)     # que exista; si no, AccountError
    _añadir_a_grupo(config.APP_GROUP, username)
    if es_admin:
        _añadir_a_grupo(config.ADMIN_GROUP, username)
    try:
        from . import espacios
        espacios.asegurar_espacio(username)
    except Exception:
        pass
    return info_usuario(username)


def retirar_de_custodia(username: str) -> None:
    """
    Saca una cuenta de la aplicación sin tocar la cuenta de Windows.

    Deja de aparecer en Custodia y pierde su condición de administrador de la
    aplicación; su carpeta personal se conserva, igual que al eliminarla.
    """
    _assert_gestionable(username)
    for grupo in (config.ADMIN_GROUP, config.APP_GROUP):
        try:
            win32net.NetLocalGroupDelMembers(config.SERVER, grupo, 3, [
                {"domainandname": _calificado(username)}
            ])
        except pywintypes.error as exc:
            if exc.winerror in _NO_ES_MIEMBRO:
                continue
            raise AccountError(
                f"No se pudo retirar '{username}' de '{grupo}': {exc.strerror}"
            ) from exc


def listar_usuarios() -> list[CuentaInfo]:
    """
    Lista solo las cuentas de la aplicación.

    Enumeramos los miembros de APP_GROUP en vez de todas las cuentas de la
    máquina: así la interfaz nunca muestra cuentas del sistema.
    """
    try:
        miembros, _, _ = win32net.NetLocalGroupGetMembers(config.SERVER, config.APP_GROUP, 1)
    except pywintypes.error as exc:
        if exc.winerror in _GRUPO_NO_EXISTE:
            return []
        raise AccountError(f"No se pudieron listar los usuarios: {exc.strerror}") from exc

    salida = []
    for m in miembros:
        nombre = m["name"].split("\\")[-1]
        try:
            salida.append(info_usuario(nombre))
        except AccountError:
            continue  # miembro huérfano; lo ignoramos en vez de romper el listado
    return sorted(salida, key=lambda c: c.username.lower())


def es_miembro_app(username: str) -> bool:
    """
    True si la cuenta pertenece a Custodia (está en APP_GROUP).

    Ante cualquier duda —la cuenta o el grupo no existen, no se pueden leer—
    devuelve False: quien decide si se entra es esta comprobación, así que en
    caso de error se niega.
    """
    try:
        return config.APP_GROUP.lower() in {g.lower() for g in _grupos_de(username)}
    except AccountError:
        return False


def es_admin(username: str) -> bool:
    """True si la cuenta pertenece al grupo de administradores de la aplicación."""
    return config.ADMIN_GROUP in _grupos_de(username)


# ---------------------------------------------------------------------------
# Grupos
# ---------------------------------------------------------------------------

def crear_grupo(nombre: str, descripcion: str = "") -> None:
    """Crea un grupo local de Windows."""
    try:
        win32net.NetLocalGroupAdd(config.SERVER, 1, {
            "name": nombre,
            "comment": descripcion or f"Custodia: {nombre}",
        })
    except pywintypes.error as exc:
        if exc.winerror in _GRUPO_YA_EXISTE:
            raise AccountError(f"El grupo '{nombre}' ya existe") from exc
        raise AccountError(f"No se pudo crear el grupo: {exc.strerror}") from exc


def eliminar_grupo(nombre: str) -> None:
    """Elimina un grupo, salvo los propios de la aplicación."""
    if nombre in (config.APP_GROUP, config.ADMIN_GROUP):
        raise ProtectedAccount(f"'{nombre}' es un grupo interno y no se puede eliminar")
    try:
        win32net.NetLocalGroupDel(config.SERVER, nombre)
    except pywintypes.error as exc:
        if exc.winerror in _GRUPO_NO_EXISTE:
            raise AccountError(f"El grupo '{nombre}' no existe") from exc
        raise AccountError(f"No se pudo eliminar el grupo: {exc.strerror}") from exc


def _añadir_a_grupo(grupo: str, username: str) -> None:
    try:
        win32net.NetLocalGroupAddMembers(config.SERVER, grupo, 3, [
            {"domainandname": _calificado(username)}
        ])
    except pywintypes.error as exc:
        # Ya es miembro: idempotencia deseable, no es un error.
        if exc.winerror in _YA_ES_MIEMBRO:
            return
        raise AccountError(
            f"No se pudo añadir '{username}' al grupo '{grupo}': {exc.strerror}"
        ) from exc


def añadir_a_grupo(grupo: str, username: str) -> None:
    """Añade un usuario de la aplicación a un grupo."""
    _assert_gestionable(username)
    _añadir_a_grupo(grupo, username)


#: Alias sin eñe. El nombre con eñe es válido en Python 3, pero un carácter no
#: ASCII en un identificador público invita a errores de codificación al
#: importarlo desde otros módulos o herramientas.
def anadir_a_grupo(grupo: str, username: str) -> None:
    """Añade un usuario de la aplicación a un grupo."""
    return añadir_a_grupo(grupo, username)


def quitar_de_grupo(grupo: str, username: str) -> None:
    """Quita un usuario de un grupo."""
    _assert_gestionable(username)
    if grupo == config.APP_GROUP:
        raise ProtectedAccount(
            f"No se puede sacar a un usuario de '{config.APP_GROUP}': dejaría de "
            "ser reconocible como cuenta de la aplicación y quedaría huérfana"
        )
    try:
        win32net.NetLocalGroupDelMembers(config.SERVER, grupo, 3, [
            {"domainandname": _calificado(username)}
        ])
    except pywintypes.error as exc:
        raise AccountError(f"No se pudo quitar del grupo: {exc.strerror}") from exc


def listar_grupos() -> list[dict]:
    """Lista los grupos locales de la máquina con su descripción."""
    try:
        grupos, _, _ = win32net.NetLocalGroupEnum(config.SERVER, 1)
    except pywintypes.error as exc:
        raise AccountError(f"No se pudieron listar los grupos: {exc.strerror}") from exc
    return [{"name": g["name"], "description": g["comment"]} for g in grupos]
