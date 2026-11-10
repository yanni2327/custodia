# -*- coding: utf-8 -*-
"""
Fixtures compartidas.

Estas pruebas crean cuentas de Windows reales y las eliminan al terminar. Por
eso exigen Windows y privilegios de administrador; en cualquier otro caso se
saltan en vez de fallar.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

es_windows = sys.platform == "win32"

pytestmark = pytest.mark.skipif(not es_windows, reason="Custodia solo funciona en Windows")


def _es_admin() -> bool:
    if not es_windows:
        return False
    import ctypes
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


requiere_admin = pytest.mark.skipif(
    not _es_admin(),
    reason="Requiere consola como administrador (crea cuentas de Windows)",
)


@pytest.fixture(autouse=True)
def sin_anclas_reales(monkeypatch):
    """Las pruebas no escriben en el Visor de eventos del equipo, salvo que lo pidan."""
    from custodia.core import config
    monkeypatch.setattr(config, "ANCLAR_BITACORA", False)


@pytest.fixture(scope="session")
def grupos_app():
    """Garantiza que existen los grupos de la aplicación."""
    from custodia.core import accounts
    accounts.asegurar_grupos()
    return True


@pytest.fixture
def usuario_prueba(grupos_app):
    """
    Crea una cuenta temporal y la elimina al terminar.

    Nombre corto a propósito: las cuentas locales de Windows están limitadas a
    20 caracteres.
    """
    from custodia.core import accounts

    nombre = "cust_t1"
    password = "Prueba.2026!SOP"

    try:
        accounts.eliminar_usuario(nombre)
    except Exception:
        pass

    cuenta = accounts.crear_usuario(nombre, password, display_name="Usuario de prueba")
    yield cuenta, password

    try:
        accounts.eliminar_usuario(nombre)
    except Exception:
        pass


@pytest.fixture
def clave_maestra(tmp_path_factory, monkeypatch):
    """
    Clave maestra de pruebas, en una ruta temporal.

    No se reutiliza la de producción: regenerarla dejaría ilegibles los
    archivos reales del usuario. Se crea una por sesión de pruebas.
    """
    from custodia.core import config, crypto

    ruta = tmp_path_factory.mktemp("clave") / "master.key"
    monkeypatch.setattr(config, "KEY_FILE", ruta)
    crypto.olvidar_clave()
    crypto.crear_clave_maestra(ruta)
    # Igual que hace la aplicación al arrancar: cargar la clave mientras
    # todavía corremos con identidad privilegiada, antes de suplantar a nadie.
    crypto.precargar_clave()
    yield ruta
    crypto.olvidar_clave()


@pytest.fixture
def raiz(tmp_path, monkeypatch):
    """Redirige STORAGE_ROOT a una carpeta temporal para no tocar la real."""
    from custodia.core import config

    almacen = tmp_path / "storage"
    almacen.mkdir()
    monkeypatch.setattr(config, "STORAGE_ROOT", almacen)
    return almacen


@pytest.fixture
def bitacora(tmp_path):
    """
    Bitácora en una base de datos temporal, aislada por prueba.

    No se usa la real: las pruebas ensucian el registro de auditoría, y ese
    archivo es evidencia. Cada prueba arranca con la tabla vacía.
    """
    from custodia.core import audit

    audit.init(tmp_path / "auditoria_de_prueba.db")
    yield tmp_path / "auditoria_de_prueba.db"
    audit.close()


# ---------------------------------------------------------------------------
# Contrato de permisos (RNF-03)
# ---------------------------------------------------------------------------

@pytest.fixture(params=["windows", "memoria"])
def backend(request, raiz):
    """
    Cada prueba del contrato se ejecuta una vez por implementación.

    Es el criterio de aceptación del RNF-03: la misma suite, sin cambios,
    contra ambos backends. Si una se desvía del contrato, la prueba falla solo
    para esa.
    """
    if request.param == "windows":
        from custodia.core.backends.windows import BackendWindows
        yield BackendWindows()
    else:
        from custodia.core.backends.memoria import BackendMemoria
        b = BackendMemoria()
        yield b
        b.limpiar()


@pytest.fixture
def sujeto(request, usuario_prueba):
    """
    Sujeto de prueba con su token de Windows.

    El doble de prueba ignora el token; el backend real lo necesita. Llevarlo
    siempre permite que el cuerpo de las pruebas del contrato sea idéntico.
    """
    from custodia.core import auth
    from custodia.core.permissions import Sujeto

    cuenta, password = usuario_prueba
    token = auth.logon(cuenta.username, password)
    yield Sujeto(cuenta.username, token)
    token.Close()


@pytest.fixture
def archivo_de_prueba(raiz, usuario_prueba):
    """
    Archivo con la herencia rota y sin permisos para el usuario de prueba.

    Romper la herencia es imprescindible: si el archivo heredara los permisos
    de la carpeta temporal, el grupo Usuarios tendría lectura y las pruebas de
    denegación pasarían sin probar nada.
    """
    from custodia.core import acl
    from custodia.core.acl import Perm

    archivo = raiz / "sujeto_de_prueba.txt"
    archivo.write_bytes(b"contenido de prueba")
    acl.establecer_permisos(
        archivo,
        [("Administrators", int(Perm.TOTAL), True, False)],
        romper_herencia=True,
    )
    return archivo
