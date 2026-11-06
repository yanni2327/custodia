# -*- coding: utf-8 -*-
"""
Sesión de usuario: la frontera entre la interfaz y el núcleo.

Esta clase existe para que **ningún archivo de la interfaz tenga que saber que
la suplantación existe**. La ventana pide "lista esta carpeta" y recibe una
lista; quién adopta la identidad del usuario, dónde empieza y dónde termina ese
bloque, es problema de aquí.

La razón no es estética. La suplantación en Windows es por hilo y hay que
revertirla siempre; si cada manejador de botón la gestionara por su cuenta,
bastaría un `return` temprano o una excepción no prevista en un solo sitio para
dejar el hilo de la interfaz corriendo con la identidad de otro usuario. Al
concentrarla en una clase, ese riesgo vive en un archivo y no en veinte.

Reparto de responsabilidades en cada método, siempre en este orden:

1. Resolver y validar la ruta —con la identidad de la aplicación—, porque
   resolver toca el disco.
2. Suplantar.
3. Ejecutar solo la operación que debe someterse a los permisos del usuario.
4. Revertir, garantizado por el `with`.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..core import (accounts, acl, audit, auth, boveda, config, crypto,
                    descargas, espacios, fsops, jail, seguridad, segundofactor)
from ..core.backends.windows import BackendWindows
from ..core.errors import (AccountError, AuthenticationError,
                           CambioDeContrasenaRequerido, CustodiaError,
                           PermissionDenied, SegundoFactorRequerido)
from ..core.fsops import NodoInfo
from ..core.impersonate import impersonate
from ..core.permissions import Accion, Sujeto


def _cerrar_token(token) -> None:
    """Libera un token del kernel sin propagar errores."""
    try:
        token.Close()
    except Exception:
        pass


@dataclass
class Sesion:
    """Un usuario autenticado y lo que puede hacer."""

    username: str
    token: object
    es_admin: bool
    #: Clave privada del usuario para el cifrado por usuario. Solo existe en
    #: memoria mientras dura la sesión; None si el modo está apagado.
    privada: object = None
    #: Contador TOTP del último código aceptado en esta sesión. Un código no
    #: sirve dos veces: ni el del inicio de sesión para una operación, ni el de
    #: una operación para la siguiente.
    ultimo_contador: int = -1

    # -- ciclo de vida ------------------------------------------------------

    @classmethod
    def iniciar(cls, username: str, password: str,
                codigo: str | None = None) -> "Sesion":
        """
        Autentica contra Windows y abre la sesión.

        El orden de las comprobaciones es deliberado:

        1. **Bloqueo.** Si la cuenta está bloqueada por intentos fallidos, ni
           siquiera se molesta a Windows: se rechaza de una vez.
        2. **Contraseña.** La valida Windows (`LogonUser`). Un fallo cuenta para
           el bloqueo.
        3. **Pertenencia.** La cuenta debe ser de Custodia (APP_GROUP); si no,
           se rechaza aunque la contraseña sea correcta.
        4. **Segundo factor.** Si la cuenta lo tiene activado y no llegó el
           código, se cierra el token y se avisa a la interfaz con
           `SegundoFactorRequerido` para que lo pida y reintente. Un código malo
           también cuenta para el bloqueo.

        :raises AuthenticationError: credenciales inválidas, cuenta inutilizable
            o cuenta bloqueada.
        :raises SegundoFactorRequerido: la contraseña fue correcta pero falta el
            código del segundo factor.
        """
        bloqueado, restante = seguridad.esta_bloqueado(username)
        if bloqueado:
            audit.registrar(username, "inicio_sesion", exito=False,
                            detalle="cuenta bloqueada")
            raise AuthenticationError(
                "La cuenta está bloqueada temporalmente por intentos fallidos. "
                f"Vuelve a intentarlo en {restante // 60 + 1} minutos."
            )

        try:
            token = auth.logon(username, password)
        except AuthenticationError:
            quedo_bloqueada, _ = seguridad.registrar_fallo(username)
            audit.registrar(username, "inicio_sesion", exito=False,
                            detalle="credenciales")
            if quedo_bloqueada:
                raise AuthenticationError(
                    "Demasiados intentos fallidos. La cuenta queda bloqueada "
                    f"{config.BLOQUEO_MIN} minutos."
                )
            raise
        except CambioDeContrasenaRequerido:
            # La contraseña (temporal) era correcta, pero Windows exige
            # cambiarla. Solo se ofrece a cuentas de Custodia.
            if not accounts.es_miembro_app(username):
                audit.registrar(username, "inicio_sesion", exito=False,
                                detalle="la cuenta no pertenece a Custodia")
                raise AuthenticationError(
                    "Esta cuenta de Windows no tiene acceso a Custodia. Pide a un "
                    "administrador de Custodia que la añada."
                )
            audit.registrar(username, "inicio_sesion", exito=False,
                            detalle="debe cambiar la contraseña")
            raise

        # Solo entran las cuentas de Custodia. Windows valida la contraseña de
        # CUALQUIER cuenta del equipo; que la contraseña sea correcta no hace a
        # nadie usuario de la aplicación. No cuenta para el bloqueo: la persona
        # sí demostró conocer su contraseña, así que tampoco se le oculta el
        # motivo.
        if not accounts.es_miembro_app(username):
            _cerrar_token(token)
            audit.registrar(username, "inicio_sesion", exito=False,
                            detalle="la cuenta no pertenece a Custodia")
            raise AuthenticationError(
                "Esta cuenta de Windows no tiene acceso a Custodia. Pide a un "
                "administrador de Custodia que la añada."
            )

        contador = -1
        if segundofactor.esta_habilitado(username):
            if codigo is None:
                _cerrar_token(token)
                raise SegundoFactorRequerido()
            contador = segundofactor.verificar_contador(username, codigo)
            if contador is None:
                _cerrar_token(token)
                quedo_bloqueada, _ = seguridad.registrar_fallo(username)
                audit.registrar(username, "fallo_segundo_factor", exito=False)
                if quedo_bloqueada:
                    raise AuthenticationError(
                        "Demasiados intentos fallidos. La cuenta queda bloqueada "
                        f"{config.BLOQUEO_MIN} minutos."
                    )
                raise AuthenticationError("El código de verificación no es correcto.")
            audit.registrar(username, "segundo_factor_ok", exito=True)

        # Acceso correcto: se borra el historial de intentos de esta cuenta.
        seguridad.limpiar(username)

        try:
            es_admin = accounts.es_admin(username)
        except Exception:
            # La cuenta existe (LogonUser lo confirmó) pero no se pudo leer su
            # pertenencia a grupos. Se asume el privilegio mínimo.
            es_admin = False

        # Idempotente: las cuentas creadas antes de que existiera el espacio
        # personal también lo reciben al entrar por primera vez.
        try:
            espacios.asegurar_espacio(username)
        except Exception:
            pass

        # Cifrado por usuario: con la contraseña a mano, se crea la identidad la
        # primera vez y se desenvuelve la clave privada, que vive en memoria
        # durante la sesión. La contraseña no se guarda.
        privada = None
        if config.CIFRADO_POR_USUARIO:
            try:
                if not boveda.tiene_identidad(username):
                    boveda.crear_identidad(username, password)
                privada = boveda.cargar_privada(username, password)
            except Exception:
                privada = None

        audit.registrar(username, "inicio_sesion", exito=True)
        return cls(username=username, token=token, es_admin=es_admin,
                   privada=privada, ultimo_contador=contador)

    # -- contraseñas ----------------------------------------------------------

    @staticmethod
    def _validar_nueva(nueva: str, anterior: str) -> None:
        error = accounts.regla_contrasena(nueva)
        if error:
            raise AccountError(error)
        if nueva == anterior:
            raise AccountError("La contraseña nueva tiene que ser distinta de la anterior.")

    @staticmethod
    def _cambiar(username: str, actual: str, nueva: str, motivo: str) -> None:
        """Cambio con la contraseña actual; los fallos cuentan para el bloqueo."""
        bloqueado, restante = seguridad.esta_bloqueado(username)
        if bloqueado:
            raise AuthenticationError(
                "La cuenta está bloqueada temporalmente por intentos fallidos. "
                f"Vuelve a intentarlo en {restante // 60 + 1} minutos."
            )
        try:
            accounts.cambiar_password_propia(username, actual, nueva)
        except AuthenticationError:
            quedo_bloqueada, _ = seguridad.registrar_fallo(username)
            audit.registrar(username, "cambiar_password", exito=False, detalle=motivo)
            if quedo_bloqueada:
                raise AuthenticationError(
                    "Demasiados intentos fallidos. La cuenta queda bloqueada "
                    f"{config.BLOQUEO_MIN} minutos."
                )
            raise
        # Con el cifrado por usuario, la clave privada va protegida por la
        # contraseña: se vuelve a proteger con la nueva para no perderla.
        if config.CIFRADO_POR_USUARIO and boveda.tiene_identidad(username):
            boveda.cambiar_contrasena(username, actual, nueva)
        seguridad.limpiar(username)
        audit.registrar(username, "cambiar_password", exito=True, detalle=motivo)

    @classmethod
    def cambiar_contrasena_obligatoria(cls, username: str, temporal: str,
                                       nueva: str) -> None:
        """Al entrar con una contraseña temporal: la cambia por la definitiva."""
        cls._validar_nueva(nueva, temporal)
        cls._cambiar(username, temporal, nueva, "cambio obligatorio al entrar")

    def cambiar_mi_contrasena(self, actual: str, nueva: str) -> None:
        """La persona cambia su propia contraseña desde su perfil."""
        self._validar_nueva(nueva, actual)
        self._cambiar(self.username, actual, nueva, "desde su perfil")

    def restablecer_contrasena(self, username: str) -> str:
        """
        Pone una contraseña temporal a OTRA cuenta (la olvidó) y la marca para
        que Windows exija cambiarla al entrar. Devuelve la temporal, que solo
        se muestra una vez al administrador; nunca se guarda ni se registra.

        También se le quita el bloqueo por intentos: lo normal es que quien
        olvidó su contraseña haya acabado bloqueado probando.
        """
        self._exigir_admin()
        if username.lower() == self.username.lower():
            raise PermissionError(
                "Tu propia contraseña se cambia desde tu perfil, no desde aquí."
            )
        temporal = accounts.contrasena_temporal()
        accounts.cambiar_password(username, temporal)
        accounts.forzar_cambio_de_contrasena(username)
        seguridad.limpiar(username)
        audit.registrar(self.username, "restablecer_contrasena", detalle=username)
        return temporal

    def pierde_cifrado_al_restablecer(self, username: str) -> bool:
        """
        Con el cifrado por usuario activo, restablecer la contraseña de otra
        persona deja inservible su clave privada (estaba protegida por la
        contraseña que nadie más conoce): sus archivos cifrados solo para ella
        no se podrán abrir. La interfaz lo avisa antes de hacerlo.
        """
        return bool(config.CIFRADO_POR_USUARIO and boveda.tiene_identidad(username))

    # -- segundo factor (2FA) ----------------------------------------------

    def segundo_factor_activo(self) -> bool:
        return segundofactor.esta_habilitado(self.username)

    def activar_segundo_factor(self) -> tuple[str, str]:
        """Genera el secreto y lo guarda; devuelve (secreto, enlace otpauth)."""
        secreto, uri = segundofactor.activar(self.username)
        audit.registrar(self.username, "segundo_factor_activado", exito=True)
        return secreto, uri

    def verificar_segundo_factor(self, codigo: str) -> bool:
        """Al activar el segundo factor: el código de prueba tampoco se reutiliza."""
        contador = segundofactor.verificar_contador(self.username, codigo)
        if contador is None:
            return False
        self.ultimo_contador = max(self.ultimo_contador, contador)
        return True

    def confirmar_operacion(self, codigo: str, operacion: str) -> str:
        """
        Comprueba el código del segundo factor antes de una operación sensible
        (eliminar, descargar, cambiar permisos…).

        Las mismas reglas que al entrar: cada fallo cuenta para el bloqueo de
        la cuenta y queda en la bitácora con la operación que se intentaba.
        Además, un código ya aceptado en esta sesión no vale otra vez.

        :return: "ok", "incorrecto" o "usado".
        :raises AuthenticationError: la cuenta está (o acaba de quedar)
            bloqueada por demasiados intentos.
        """
        bloqueado, restante = seguridad.esta_bloqueado(self.username)
        if bloqueado:
            raise AuthenticationError(
                "La cuenta está bloqueada temporalmente por intentos fallidos. "
                f"Vuelve a intentarlo en {restante // 60 + 1} minutos."
            )

        contador = segundofactor.verificar_contador(self.username, codigo)
        if contador is not None and contador <= self.ultimo_contador:
            # Válido, pero ya usado: no es un intento de adivinar, no penaliza.
            return "usado"
        if contador is None:
            quedo_bloqueada, _ = seguridad.registrar_fallo(self.username)
            audit.registrar(self.username, "fallo_segundo_factor", exito=False,
                            detalle=operacion)
            if quedo_bloqueada:
                raise AuthenticationError(
                    "Demasiados códigos incorrectos. La cuenta queda bloqueada "
                    f"{config.BLOQUEO_MIN} minutos."
                )
            return "incorrecto"

        self.ultimo_contador = contador
        seguridad.limpiar(self.username)
        audit.registrar(self.username, "segundo_factor_ok", exito=True,
                        detalle=operacion)
        return "ok"

    def desactivar_segundo_factor(self) -> None:
        segundofactor.desactivar(self.username)
        audit.registrar(self.username, "segundo_factor_desactivado", exito=True)

    # -- descargas (exportación de copias) ---------------------------------

    def tiene_clave_descarga(self) -> bool:
        return descargas.tiene_clave(self.username)

    def establecer_clave_descarga(self, clave: str) -> None:
        descargas.establecer_clave(self.username, clave)
        audit.registrar(self.username, "clave_descarga_activada", exito=True)

    def quitar_clave_descarga(self) -> None:
        descargas.quitar_clave(self.username)
        audit.registrar(self.username, "clave_descarga_desactivada", exito=True)

    def verificar_clave_descarga(self, clave: str) -> bool:
        return descargas.verificar_clave(self.username, clave)

    def verificar_password(self, password: str) -> bool:
        """Confirma la contraseña de Windows (respaldo del paso de descarga)."""
        try:
            token = auth.logon(self.username, password)
        except Exception:
            return False
        _cerrar_token(token)
        return True

    def estado_descargas(self) -> tuple[bool, int]:
        return descargas.estado(self.username)

    def registrar_descarga(self, ruta_virtual: str, motivo: str = "") -> tuple[bool, int]:
        """Deja la descarga en la bitácora con su motivo y aplica el límite."""
        return descargas.registrar(self.username, ruta_virtual, motivo)

    # -- bloqueo por inactividad -------------------------------------------

    def registrar_bloqueo(self, motivo: str) -> None:
        """Deja en la bitácora que la pantalla se bloqueó y por qué."""
        audit.registrar(self.username, "bloqueo_pantalla", exito=True,
                        detalle=motivo)

    def cuenta_bloqueada(self) -> bool:
        """True si la cuenta quedó bloqueada por intentos fallidos."""
        return seguridad.esta_bloqueado(self.username)[0]

    def desbloquear(self, password: str, codigo: str | None = None) -> None:
        """
        Comprueba las credenciales para reanudar una sesión bloqueada.

        Aplica las mismas reglas que el inicio de sesión —bloqueo por intentos,
        contraseña validada por Windows y segundo factor si está activo—, de
        modo que la pantalla de bloqueo no sea un atajo para adivinar la
        contraseña sin límite. No crea una sesión nueva: el token original
        sigue siendo el de la sesión.

        :raises AuthenticationError: credenciales inválidas o cuenta bloqueada.
        :raises SegundoFactorRequerido: falta el código del segundo factor.
        """
        bloqueado, restante = seguridad.esta_bloqueado(self.username)
        if bloqueado:
            audit.registrar(self.username, "desbloqueo", exito=False,
                            detalle="cuenta bloqueada")
            raise AuthenticationError(
                "La cuenta está bloqueada temporalmente por intentos fallidos. "
                f"Vuelve a intentarlo en {restante // 60 + 1} minutos."
            )

        try:
            token = auth.logon(self.username, password)
        except AuthenticationError:
            quedo_bloqueada, _ = seguridad.registrar_fallo(self.username)
            audit.registrar(self.username, "desbloqueo", exito=False,
                            detalle="credenciales")
            if quedo_bloqueada:
                raise AuthenticationError(
                    "Demasiados intentos fallidos. La cuenta queda bloqueada "
                    f"{config.BLOQUEO_MIN} minutos."
                )
            raise AuthenticationError("La contraseña no es correcta.")
        _cerrar_token(token)

        if segundofactor.esta_habilitado(self.username):
            if codigo is None:
                raise SegundoFactorRequerido()
            if not segundofactor.verificar(self.username, codigo):
                quedo_bloqueada, _ = seguridad.registrar_fallo(self.username)
                audit.registrar(self.username, "fallo_segundo_factor", exito=False,
                                detalle="desbloqueo")
                if quedo_bloqueada:
                    raise AuthenticationError(
                        "Demasiados intentos fallidos. La cuenta queda bloqueada "
                        f"{config.BLOQUEO_MIN} minutos."
                    )
                raise AuthenticationError("El código de verificación no es correcto.")

        seguridad.limpiar(self.username)
        audit.registrar(self.username, "desbloqueo", exito=True)

    def cerrar(self) -> None:
        """Libera el token de Windows y la clave privada. Llamar al salir."""
        audit.registrar(self.username, "cierre_sesion", exito=True)
        # La clave privada no debe sobrevivir a la sesión en memoria.
        self.privada = None
        try:
            self.token.Close()
        except Exception:
            pass

    @property
    def sujeto(self) -> Sujeto:
        return Sujeto(self.username, self.token)

    # -- operaciones sobre archivos ----------------------------------------

    # -- alcance de un usuario normal ----------------------------------------
    #
    # Regla del caso de estudio: un usuario estándar solo trabaja en SU carpeta
    # y en la COMPARTIDA. El kernel ya lo impone (la raíz no es listable para
    # él y las carpetas ajenas no le dan acceso); aquí la interfaz lo refleja:
    # la raíz se le presenta con esas dos carpetas y nada más, sin enumerarla.

    def raices_visibles(self) -> list[str] | None:
        """Carpetas de primer nivel a las que llega esta cuenta (None = todas)."""
        if self.es_admin:
            return None
        return [f"/{self.username}", f"/{espacios.COMPARTIDA}"]

    @staticmethod
    def _canonica(ruta_virtual: str) -> str:
        return jail.to_virtual(jail.resolve(ruta_virtual)).rstrip("/").lower() or "/"

    def es_espacio_base(self, ruta_virtual: str) -> bool:
        """¿Es la carpeta personal o la compartida (no lo que tienen dentro)?"""
        raices = self.raices_visibles()
        if raices is None:
            return False
        return self._canonica(ruta_virtual) in {r.lower() for r in raices}

    def _raiz_de_usuario(self) -> list[NodoInfo]:
        nodos = []
        for ruta in self.raices_visibles() or []:
            try:
                nodos.append(self.info(ruta))
            except CustodiaError:
                continue   # aún no existe o no se puede leer: no se muestra
        return nodos

    def _proteger_raiz_propia(self, ruta_virtual: str, que: str) -> None:
        if self.es_espacio_base(ruta_virtual):
            audit.registrar(self.username, que, ruta_virtual, exito=False,
                            detalle="espacio base protegido")
            raise PermissionDenied(
                "Tu carpeta personal y la compartida son fijas: no se pueden "
                "eliminar ni renombrar. Sí puedes trabajar con lo que contienen."
            )

    def listar(self, ruta_virtual: str) -> list[NodoInfo]:
        if not self.es_admin and self._canonica(ruta_virtual) == "/":
            return self._raiz_de_usuario()
        ruta = jail.resolve(ruta_virtual)
        with impersonate(self.token):
            return fsops.listar(ruta)

    def _proteger_raiz_del_almacen(self, ruta_padre: str, que: str) -> None:
        """Un usuario normal no crea nada en la raíz: solo en sus dos carpetas."""
        if not self.es_admin and self._canonica(ruta_padre) == "/":
            audit.registrar(self.username, que, ruta_padre, exito=False,
                            detalle="la raíz del almacén es solo de administración")
            raise PermissionDenied(
                "En la raíz del almacén solo están tu carpeta y la compartida. "
                "Entra en una de ellas para crear o añadir contenido."
            )

    def crear_carpeta(self, ruta_virtual: str, nombre: str) -> NodoInfo:
        self._proteger_raiz_del_almacen(ruta_virtual, "crear_carpeta")
        destino = jail.resolve(ruta_virtual) / nombre
        jail.resolve(f"{ruta_virtual}/{nombre}")   # valida el nombre
        with impersonate(self.token):
            return fsops.crear_carpeta(destino)

    def leer(self, ruta_virtual: str) -> bytes:
        ruta = jail.resolve(ruta_virtual)
        with impersonate(self.token):
            blob = fsops.leer(ruta, descifrar=False)
        # El descifrado va fuera de la suplantación: con cifrado por usuario usa
        # la clave privada en memoria (sin tocar disco); con la clave maestra,
        # el caché ya cargado. Un archivo v2 lo abre la bóveda; lo demás, la
        # clave maestra (así se siguen leyendo archivos previos).
        if (config.CIFRADO_POR_USUARIO and self.privada is not None
                and boveda.es_v2(blob)):
            return boveda.descifrar(blob, self.username, self.privada)
        return crypto.descifrar(blob)

    def escribir(self, ruta_virtual: str, datos: bytes,
                 sobrescribir: bool = False) -> NodoInfo:
        padre = ruta_virtual.rstrip("/").rsplit("/", 1)[0] or "/"
        self._proteger_raiz_del_almacen(padre, "escribir")
        ruta = jail.resolve(ruta_virtual)
        if config.CIFRADO_POR_USUARIO and self.privada is not None:
            # Se envuelve con la identidad del usuario ANTES de suplantar
            # (operación de la aplicación, no del usuario) y se escribe el blob
            # ya cifrado, pidiéndole a fsops que no vuelva a cifrar.
            blob = boveda.cifrar(datos, self._destinatarios_para(ruta))
            with impersonate(self.token):
                return fsops.escribir(ruta, blob, sobrescribir=sobrescribir,
                                      cifrar=False)
        with impersonate(self.token):
            return fsops.escribir(ruta, datos, sobrescribir=sobrescribir)

    def _destinatarios_para(self, ruta) -> dict:
        """
        Para quién se cifra un archivo: el que escribe y, si ya existía, quienes
        ya tenían acceso (para no quitárselo al sobrescribir).
        """
        usuarios = {self.username.lower()}
        try:
            with impersonate(self.token):
                viejo = ruta.read_bytes() if ruta.exists() and ruta.is_file() else None
        except Exception:
            viejo = None
        if viejo and boveda.es_v2(viejo):
            usuarios.update(boveda.destinatarios(viejo))

        destinatarios = {}
        for usuario in usuarios:
            publica = boveda.publica_de(usuario)
            if publica is not None:
                destinatarios[usuario] = publica
        return destinatarios

    def compartir(self, ruta_virtual: str, nuevo_usuario: str) -> None:
        """
        Da acceso criptográfico de un ARCHIVO a otra persona.

        Reenvuelve la clave del archivo con la pública del nuevo usuario. Solo
        funciona si quien comparte puede leer el archivo (tiene su propia clave
        envuelta dentro) y el nuevo usuario ya tiene identidad. Se aplica a
        archivos; las carpetas no se cifran.
        """
        if not (config.CIFRADO_POR_USUARIO and self.privada is not None):
            return
        nueva_publica = boveda.publica_de(nuevo_usuario)
        if nueva_publica is None:
            return
        ruta = jail.resolve(ruta_virtual)
        with impersonate(self.token):
            if not ruta.is_file():
                return
            blob = ruta.read_bytes()
        if not boveda.es_v2(blob):
            return
        try:
            nuevo = boveda.conceder(blob, self.username, self.privada,
                                    nuevo_usuario, nueva_publica)
        except Exception:
            return   # quien comparte no podía leerlo; nada que reenvolver
        with impersonate(self.token):
            fsops.escribir(ruta, nuevo, sobrescribir=True, cifrar=False)

    def eliminar(self, ruta_virtual: str, recursivo: bool = False) -> None:
        # Un usuario es propietario de su carpeta y el kernel le dejaría
        # borrarla entera; se impide aquí porque es su espacio base.
        self._proteger_raiz_propia(ruta_virtual, "eliminar")
        ruta = jail.resolve(ruta_virtual)
        with impersonate(self.token):
            fsops.eliminar(ruta, recursivo=recursivo)

    def renombrar(self, ruta_virtual: str, nuevo_nombre: str) -> NodoInfo:
        self._proteger_raiz_propia(ruta_virtual, "renombrar")
        ruta = jail.resolve(ruta_virtual)
        with impersonate(self.token):
            return fsops.renombrar(ruta, nuevo_nombre)

    def info(self, ruta_virtual: str) -> NodoInfo:
        ruta = jail.resolve(ruta_virtual)
        with impersonate(self.token):
            return fsops.info(ruta)

    # -- permisos (RF-07) ---------------------------------------------------

    def permisos_efectivos(self, ruta_virtual: str) -> set[Accion]:
        """
        Qué puede hacer este usuario aquí.

        Sin suplantar: el backend recibe el token como dato y suplanta él mismo
        lo justo para el sondeo. Llamarlo desde dentro de una suplantación
        anidaría dos y el propio backend lo rechaza.
        """
        return BackendWindows().permisos_efectivos(self.sujeto, jail.resolve(ruta_virtual))

    def propietario(self, ruta_virtual: str) -> str:
        """
        Quién es el dueño del objeto.

        Lo lee la aplicación, no el usuario suplantado: el propietario es un
        metadato que la interfaz necesita mostrar incluso para elementos que la
        persona no puede abrir.
        """
        return acl.propietario(jail.resolve(ruta_virtual))

    def entradas_de_permisos(self, ruta_virtual: str) -> list[acl.Entrada]:
        """La DACL completa. Para el panel de administración de permisos."""
        return acl.leer_permisos(jail.resolve(ruta_virtual))

    def escribir_permisos(self, ruta_virtual: str,
                          entradas: list[tuple[str, int, bool, bool]],
                          romper_herencia: bool = False) -> None:
        """
        Reescribe la lista de permisos de un elemento (RF-06).

        **Se hace bajo suplantación, no con los privilegios de la aplicación.**
        Cambiar una DACL requiere el derecho WRITE_DAC, que en Windows tienen
        los administradores y el propietario del objeto. Al suplantar, es el
        kernel quien decide si esta persona puede cambiar estos permisos, igual
        que decide si puede leer un archivo.

        La alternativa —comprobar `es_admin` y escribir la DACL con los
        privilegios de la aplicación— habría sido volver a poner la
        autorización en manos de un `if` nuestro, justo lo que el proyecto
        evita. Además dejaría fuera un caso legítimo: el dueño de su propia
        carpeta puede cambiarle los permisos sin ser administrador.

        Los nombres se traducen a SID **antes** de suplantar: buscar una cuenta
        consulta la base de datos de seguridad local, y no es la operación que
        queremos someter a los permisos del usuario.
        """
        ruta = jail.resolve(ruta_virtual)

        resueltas = [
            (accounts.sid_de(principal) if not principal.upper().startswith("S-1-")
             else principal, mascara, permitir, hereda)
            for principal, mascara, permitir, hereda in entradas
        ]

        try:
            with impersonate(self.token):
                acl.establecer_permisos(ruta, resueltas,
                                        romper_herencia=romper_herencia)
        except Exception as exc:
            audit.registrar(self.username, "cambiar_permisos", ruta_virtual,
                            exito=False, detalle=f"{type(exc).__name__}: {exc}")
            raise

        audit.registrar(self.username, "cambiar_permisos", ruta_virtual,
                        exito=True, detalle=f"{len(entradas)} entradas")

        # Cifrado por usuario: dar permiso NTFS a alguien no basta si el archivo
        # está cifrado para destinatarios concretos; también hay que envolverle
        # la clave. Mejor esfuerzo y por archivo (las carpetas no se cifran); si
        # el nuevo usuario aún no tiene identidad, se comparte cuando la cree.
        if config.CIFRADO_POR_USUARIO and self.privada is not None:
            for principal, _mascara, permitir, _hereda in entradas:
                if permitir and not str(principal).upper().startswith("S-1-"):
                    try:
                        self.compartir(ruta_virtual, principal)
                    except Exception:
                        pass

    # -- administración de cuentas (RF-01, RF-02) ---------------------------
    #
    # Asimetría honesta, y conviene documentarla: el acceso a los archivos lo
    # autoriza el kernel, pero crear cuentas de Windows exige que el PROCESO
    # esté elevado, cosa que es cierta sea quien sea el que inició sesión. Aquí
    # no hay un mecanismo del sistema operativo al que delegar la decisión, así
    # que la comprobación es de la aplicación: `es_admin`. Es el único punto
    # del programa donde la autorización no la da Windows.

    def _exigir_admin(self) -> None:
        if not self.es_admin:
            raise PermissionError(
                "Solo los miembros del grupo de administradores de Custodia "
                "pueden administrar cuentas."
            )

    def listar_usuarios(self) -> list:
        return accounts.listar_usuarios()

    def listar_grupos(self) -> list[dict]:
        return accounts.listar_grupos()

    def crear_usuario(self, username: str, password: str, es_admin: bool = False):
        self._exigir_admin()
        cuenta = accounts.crear_usuario(username, password, es_admin=es_admin)
        audit.registrar(self.username, "crear_usuario", detalle=username)
        return cuenta

    def eliminar_usuario(self, username: str) -> None:
        self._exigir_admin()
        accounts.eliminar_usuario(username)
        audit.registrar(self.username, "eliminar_usuario", detalle=username)

    def cambiar_password(self, username: str, password: str) -> None:
        self._exigir_admin()
        accounts.cambiar_password(username, password)
        audit.registrar(self.username, "cambiar_password", detalle=username)

    def cuentas_incorporables(self) -> list[dict]:
        self._exigir_admin()
        return accounts.cuentas_incorporables()

    def incorporar_usuario(self, username: str, es_admin: bool = False):
        """Da de alta en Custodia una cuenta de Windows que ya existía."""
        self._exigir_admin()
        cuenta = accounts.incorporar_usuario(username, es_admin=es_admin)
        audit.registrar(self.username, "incorporar_usuario",
                        detalle=f"{username} ({'administrador' if es_admin else 'usuario'})")
        return cuenta

    def retirar_usuario(self, username: str) -> None:
        """
        Saca una cuenta de Custodia sin tocar la cuenta de Windows. Mismas
        salvaguardas que con el grupo de administradores: nadie se retira a
        sí mismo y nunca se retira al último administrador.
        """
        self._exigir_admin()
        if username.lower() == self.username.lower():
            raise PermissionError(
                "No puedes retirarte a ti mismo. Pídeselo a otro administrador."
            )
        admins = [c for c in accounts.listar_usuarios() if c.es_admin]
        if any(c.username.lower() == username.lower() for c in admins) and len(admins) <= 1:
            raise PermissionError(
                "Es el único administrador. Haz administradora a otra cuenta antes "
                "de retirarla."
            )
        accounts.retirar_de_custodia(username)
        audit.registrar(self.username, "retirar_usuario", detalle=username)

    def segundo_factor_de(self, username: str) -> bool:
        """Si otra cuenta tiene la verificación en dos pasos activada."""
        return segundofactor.esta_habilitado(username)

    def restablecer_segundo_factor(self, username: str) -> None:
        """
        Quita la verificación en dos pasos de OTRA cuenta (p. ej. perdió el
        teléfono). La persona la vuelve a configurar con un QR nuevo la próxima
        vez que la necesite; el secreto anterior deja de valer, así que un
        teléfono perdido ya no sirve para nada.

        No se permite sobre la propia cuenta: eso se hace desde el perfil, con
        el código, para que nadie con una sesión abierta se la quite a sí mismo
        por esta vía.
        """
        self._exigir_admin()
        if username.lower() == self.username.lower():
            raise PermissionError(
                "Tu propia verificación se gestiona desde tu perfil, no desde aquí."
            )
        segundofactor.desactivar(username)
        audit.registrar(self.username, "segundo_factor_restablecido",
                        exito=True, detalle=username)

    def crear_grupo(self, nombre: str, descripcion: str = "") -> None:
        self._exigir_admin()
        accounts.crear_grupo(nombre, descripcion)
        audit.registrar(self.username, "crear_grupo", detalle=nombre)

    def asignar_a_grupo(self, grupo: str, username: str) -> None:
        self._exigir_admin()
        accounts.anadir_a_grupo(grupo, username)
        audit.registrar(self.username, "asignar_grupo",
                        detalle=f"{username} -> {grupo}")

    def quitar_de_grupo(self, grupo: str, username: str) -> None:
        """
        Saca a una cuenta de un grupo: pierde lo que ese grupo le daba.

        Dos salvaguardas para no dejar la aplicación sin administración:
        nadie se saca a sí mismo del grupo de administradores (lo hace otro
        administrador), y nunca se saca al último administrador.
        """
        self._exigir_admin()
        if grupo.lower() == config.ADMIN_GROUP.lower():
            if username.lower() == self.username.lower():
                raise PermissionError(
                    "No puedes quitarte a ti mismo de los administradores. "
                    "Pídeselo a otro administrador."
                )
            admins = [c for c in accounts.listar_usuarios() if c.es_admin]
            if len(admins) <= 1:
                raise PermissionError(
                    "Es el único administrador. Haz administradora a otra cuenta "
                    "antes de quitarle este grupo."
                )
        accounts.quitar_de_grupo(grupo, username)
        audit.registrar(self.username, "quitar_grupo",
                        detalle=f"{username} <- {grupo}")

    def eliminar_grupo(self, nombre: str) -> None:
        """Elimina un grupo; los dos internos de Custodia están protegidos."""
        self._exigir_admin()
        accounts.eliminar_grupo(nombre)
        audit.registrar(self.username, "eliminar_grupo", detalle=nombre)

    @staticmethod
    def grupos_internos() -> tuple[str, str]:
        """Los grupos que Custodia necesita y no se pueden tocar a mano."""
        return config.APP_GROUP, config.ADMIN_GROUP

    def bitacora(self, solo_denegados: bool = False, limite: int = 200) -> list[dict]:
        """La bitácora completa es información administrativa."""
        self._exigir_admin()
        return audit.consultar(solo_denegados=solo_denegados, limite=limite)


def arrancar_nucleo() -> None:
    """
    Prepara el núcleo. **Llamar una vez al inicio, antes de autenticar.**

    El orden importa y es el mismo problema tres veces: la clave maestra y la
    base de datos de la bitácora viven en carpetas donde solo la aplicación
    tiene permiso, así que ambas deben abrirse ahora, mientras el proceso
    conserva su identidad privilegiada. Después, dentro de las suplantaciones,
    solo se usan los recursos ya abiertos.
    """
    audit.init()
    crypto.precargar_clave()
    # Se reescribe la lista de permisos de la raíz en cada arranque (idempotente
    # y barato). Así los almacenes creados con la regla anterior —que dejaba a
    # los usuarios listar la raíz y crear carpetas en ella— quedan corregidos
    # sin tener que reinstalar. Nunca impide arrancar.
    try:
        if config.STORAGE_ROOT.exists():
            espacios.preparar_raiz()
    except Exception:
        pass


def detener_nucleo() -> None:
    """Vacía la bitácora y cierra sus recursos. Llamar al salir."""
    audit.close()
    crypto.olvidar_clave()


def hay_privilegios() -> bool:
    """
    ¿Corre el proceso como administrador?

    Sin esto no se pueden crear cuentas ni escribir ACL. La interfaz avisa al
    arrancar en lugar de dejar que el usuario descubra el problema al pulsar un
    botón y recibir un error incomprensible.
    """
    import ctypes
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def raiz_lista() -> bool:
    """¿Está inicializado el almacén? Falso si nunca se ejecutó el bootstrap."""
    return Path(config.STORAGE_ROOT).exists() and Path(config.KEY_FILE).exists()
