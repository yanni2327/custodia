# -*- coding: utf-8 -*-
"""
Punto de entrada de la aplicación.

El orden de arranque no es arbitrario:

1. Comprobar privilegios y almacén. Si falta algo, decirlo ahora con una
   instrucción concreta, en vez de dejar que el usuario lo descubra al pulsar
   un botón y recibir un error del sistema operativo.
2. Preparar el núcleo (bitácora y clave maestra) **antes de autenticar**,
   mientras el proceso conserva su identidad privilegiada.
3. Pedir credenciales.
4. Abrir la ventana.
"""
from __future__ import annotations

import sys

from pathlib import Path

from PySide6.QtCore import QEvent, QObject, QSettings
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication, QWidget

from ..core import accounts, audit, config, crypto, espacios, respaldo
from . import avisos, estilo, iconos
from .login import DialogoIngreso
from .sesion import arrancar_nucleo, detener_nucleo, hay_privilegios, raiz_lista
from .ventana import VentanaPrincipal


def _primer_arranque() -> bool:
    """
    Prepara el equipo la primera vez que se abre la aplicación.

    Existe por el criterio de aceptación del RNF-07: el ejecutable debe
    funcionar en un equipo limpio, sin Python, y ahí nadie puede ejecutar el
    script de inicialización. La aplicación hace lo mismo que hace
    `bootstrap.py`, pero preguntando.

    Se pide una cuenta administradora en el mismo paso: un almacén preparado al
    que nadie puede entrar no sirve de nada, y sin Python no hay forma de
    crearla después desde fuera.

    :return: True si el equipo quedó listo.
    """
    if not avisos.confirmar(
        None, "Primer arranque de Custodia",
        "Este equipo todavía no está preparado. Custodia va a crear el almacén "
        f"en {config.STORAGE_ROOT}, los grupos locales de Windows de la "
        "aplicación, una clave de cifrado protegida por el propio Windows y la "
        "bitácora de auditoría.\n\n¿Lo preparo ahora?",
        aceptar="Sí, preparar", cancelar="Ahora no",
    ):
        return False

    try:
        accounts.asegurar_grupos()
        if not config.KEY_FILE.exists():
            crypto.crear_clave_maestra()
        audit.init()
        espacios.preparar_todo([c.username for c in accounts.listar_usuarios()])
    except Exception as exc:
        avisos.error(None, "No se pudo preparar el equipo", str(exc))
        return False
    finally:
        audit.close()

    return _crear_primer_administrador()


def _preparar_sin_clave() -> bool:
    """
    Falta `master.key`, pero el almacén ya tiene archivos cifrados.

    No se genera otra clave: lo que se escribiera con ella se perdería al
    restaurar el respaldo. Solo se asegura que alguien pueda entrar a hacerlo,
    también en un equipo nuevo al que se copió el almacén.
    """
    try:
        accounts.asegurar_grupos()
    except Exception as exc:
        avisos.error(None, "No se pudo preparar el equipo", str(exc))
        return False
    return _crear_primer_administrador()


def _crear_primer_administrador() -> bool:
    """Pide una cuenta administradora, repitiendo hasta que Windows la acepte."""
    if any(c.es_admin for c in accounts.listar_usuarios()):
        return True   # ya hay administrador: nada que pedir

    while True:
        usuario = avisos.pedir_texto(
            None, "Cuenta administradora", "Nombre de usuario",
            descripcion="Nombre para la primera cuenta administradora. Se crea "
                        "como cuenta local de Windows (máximo 20 caracteres)."
        )
        if usuario is None:
            avisos.info(
                None, "Sin administrador",
                "El almacén quedó preparado, pero sin ninguna cuenta. Vuelve a "
                "abrir Custodia para crearla."
            )
            return False
        if not usuario.strip():
            continue

        password = avisos.pedir_texto(
            None, "Contraseña", f"Contraseña para {usuario.strip()}",
            password=True
        )
        if password is None:
            continue

        try:
            accounts.crear_usuario(usuario.strip(), password, es_admin=True)
        except Exception as exc:
            # Lo más habitual: la contraseña no cumple la política del equipo.
            # Se vuelve a preguntar en vez de abortar todo el arranque.
            avisos.error(None, "No se pudo crear la cuenta", str(exc))
            continue

        # Aparte: la cuenta ya existe, así que volver a pedirla solo daría
        # «ya existe». Se avisa y se sigue.
        try:
            espacios.asegurar_espacio(usuario.strip())
        except Exception as exc:
            avisos.advertencia(None, "La carpeta personal quedó incompleta", str(exc))
        return True


def _cargar_fuente() -> str:
    """
    Carga Inter (empaquetada con la aplicación) y devuelve su familia.

    Inter es una tipografía de interfaz moderna y abierta; unifica el aspecto
    del programa y evita depender de la fuente del sistema. Si por lo que sea no
    se puede cargar, se cae a la fuente de Windows, así que nunca rompe.

    La ruta se resuelve junto a este archivo, que es donde PyInstaller coloca
    el recurso (ver custodia.spec), de modo que funciona igual en desarrollo y
    en el ejecutable.
    """
    try:
        ruta = Path(__file__).resolve().parent / "recursos" / "Inter.ttf"
        ident = QFontDatabase.addApplicationFont(str(ruta))
        familias = QFontDatabase.applicationFontFamilies(ident)
        if familias:
            return familias[0]
    except Exception:
        pass
    return "Segoe UI Variable Text"


class _FiltroBarraTitulo(QObject):
    """
    Aplica el color de barra de título a cada ventana al mostrarse.

    Las ventanas (principal, diálogos, avisos) nacen en distintos puntos del
    programa; en vez de recordar teñir cada una, un único filtro a nivel de
    aplicación lo hace cuando cualquiera de ellas se muestra.
    """

    def eventFilter(self, obj: QObject, evento: QEvent) -> bool:
        if (evento.type() == QEvent.Type.Show
                and isinstance(obj, QWidget) and obj.isWindow()):
            estilo.tenir_barra_titulo(obj)
        return False


def _ingresar():
    """
    Muestra el inicio de sesión y devuelve la sesión abierta, o None.

    Usa la pantalla nueva en QML. Si Qt Quick no puede arrancar en este equipo
    (por ejemplo, un controlador gráfico muy antiguo o una máquina virtual sin
    aceleración), se cae al diálogo clásico en vez de dejar a nadie fuera.
    """
    try:
        from .ingreso_qml import VentanaIngreso
        ingreso = VentanaIngreso()
    except Exception:
        ingreso = None

    if ingreso is not None:
        return ingreso.sesion if ingreso.ejecutar() else None

    dialogo = DialogoIngreso()
    if dialogo.exec() != DialogoIngreso.DialogCode.Accepted:
        return None
    return dialogo.sesion


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Custodia")
    # Tipografía: Inter, cargada desde el recurso empaquetado. La de Qt por
    # defecto en Windows es más pequeña y densa, y es buena parte de lo que
    # hace que una aplicación Qt se vea anticuada antes de tocar un color.
    app.setFont(QFont(_cargar_fuente(), 10))

    # Tema: se recuerda entre sesiones. Se fija la PALETA además de la hoja de
    # estilo —imprescindible en modo oscuro, o los huecos sin regla propia
    # salen blancos— antes de mostrar nada.
    ajustes = QSettings("Custodia", "Custodia")
    tema = ajustes.value("tema", "oscuro")
    if tema not in ("oscuro", "claro"):
        tema = "oscuro"
    estilo.aplicar(tema)
    app.setPalette(estilo.paleta())
    app.setStyleSheet(estilo.HOJA)

    # El logo también como icono de las ventanas, la barra de tareas y Alt+Tab,
    # en varios tamaños (el mismo que el del ejecutable).
    app.setWindowIcon(iconos.icono_ventana())

    # Barra de título nativa acorde al tema (evita la franja blanca en oscuro).
    filtro_barra = _FiltroBarraTitulo()
    app.installEventFilter(filtro_barra)

    if not hay_privilegios():
        avisos.error(
            None, "Custodia necesita privilegios de administrador",
            "Custodia administra cuentas de Windows y permisos NTFS, y ambas "
            "cosas requieren elevación.\n\n"
            "Cierra la aplicación y ábrela con «Ejecutar como administrador»."
        )
        return 1

    if respaldo.clave_perdida():
        if not _preparar_sin_clave():
            return 1
    elif not raiz_lista() and not _primer_arranque():
        return 1

    arrancar_nucleo()
    try:
        # Bucle de sesiones: «Cerrar sesión» vuelve al ingreso; cerrar la
        # ventana con la X (o «Salir» en el ingreso) termina la aplicación.
        while True:
            sesion = _ingresar()
            if sesion is None:
                return 0

            try:
                ventana = VentanaPrincipal(sesion)
            except Exception as exc:
                # Sin consola, una excepción aquí cerraría la aplicación sin
                # explicación. Se dice qué pasó y se libera la sesión.
                sesion.cerrar()
                avisos.error(None, "No se pudo abrir la ventana principal", str(exc))
                return 1
            ventana.show()
            codigo = app.exec()
            cerro_sesion = ventana.cerro_sesion
            ventana.deleteLater()
            if not cerro_sesion:
                return codigo
    finally:
        detener_nucleo()


if __name__ == "__main__":
    sys.exit(main())
