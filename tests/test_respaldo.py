# -*- coding: utf-8 -*-
"""
Pruebas del respaldo y la recuperación de la clave maestra (control C13).

Usan una clave, un almacén y una bitácora temporales: nunca la clave real. La
sesión se construye sin token porque estas operaciones no suplantan a nadie.
"""
from __future__ import annotations

import base64
import os
import time

import pytest

from conftest import pytestmark, requiere_admin  # noqa: F401

PASSWORD = "recuperacion-de-prueba-2026"


def _sesion(es_admin: bool = True):
    from custodia.gui.sesion import Sesion
    return Sesion(username="admin_prueba" if es_admin else "usuario_prueba",
                  token=None, es_admin=es_admin)


def _clave_actual() -> bytes:
    from custodia.core import crypto
    return crypto.clave_para_respaldo()


def _archivo_cifrado(raiz, nombre: str = "expediente.txt",
                     contenido: bytes = b"contenido confidencial"):
    from custodia.core import crypto
    ruta = raiz / nombre
    ruta.write_bytes(crypto.cifrar(contenido))
    return ruta


def _cambiar_de_clave() -> None:
    """Simula el equipo donde la clave en uso ya no es la del respaldo."""
    from custodia.core import config, crypto
    crypto.olvidar_clave()
    crypto.crear_clave_maestra(config.KEY_FILE, forzar=True)
    crypto.precargar_clave()


def _foto(carpeta) -> dict:
    """Contenido de una carpeta, para comprobar que no se escribió nada."""
    return {p.name: p.read_bytes() for p in carpeta.iterdir()}


def _eventos(accion: str) -> list[dict]:
    from custodia.core import audit
    audit.flush()
    return audit.consultar(accion=accion)


@pytest.fixture
def respaldo_exportado(clave_maestra, raiz, bitacora, tmp_path):
    destino = tmp_path / "respaldo.custodiakey"
    _sesion().exportar_respaldo_clave(PASSWORD, destino)
    return destino


# ---------------------------------------------------------------------------
# Ida y vuelta
# ---------------------------------------------------------------------------

@requiere_admin
def test_ida_y_vuelta(clave_maestra, raiz, bitacora, tmp_path):
    from custodia.core import crypto
    from custodia.core.errors import CryptoError

    original = b"expediente que debe sobrevivir a la clave"
    archivo = _archivo_cifrado(raiz, contenido=original)
    destino = tmp_path / "respaldo.custodiakey"
    sesion = _sesion()

    sesion.exportar_respaldo_clave(PASSWORD, destino)
    _cambiar_de_clave()
    with pytest.raises(CryptoError):
        crypto.descifrar(archivo.read_bytes())

    preparada = sesion.preparar_restauracion_clave(destino, PASSWORD)
    assert preparada.verificada and preparada.reemplaza
    sesion.aplicar_restauracion_clave(preparada)

    # Sin reiniciar: el caché ya tiene la clave restaurada.
    assert crypto.descifrar(archivo.read_bytes()) == original

    # Tras un reinicio: el blob en disco también es correcto.
    crypto.olvidar_clave()
    crypto.precargar_clave()
    assert crypto.descifrar(archivo.read_bytes()) == original


@requiere_admin
def test_restaura_en_equipo_sin_clave(respaldo_exportado, clave_maestra, raiz):
    from custodia.core import crypto

    original = b"archivo del equipo anterior"
    archivo = _archivo_cifrado(raiz, contenido=original)
    clave_maestra.unlink()
    crypto.olvidar_clave()

    sesion = _sesion()
    preparada = sesion.preparar_restauracion_clave(respaldo_exportado, PASSWORD)
    assert not preparada.reemplaza
    sesion.aplicar_restauracion_clave(preparada)

    assert crypto.descifrar(archivo.read_bytes()) == original
    assert not list(clave_maestra.parent.glob("*.anterior-*"))


@requiere_admin
def test_almacen_vacio_no_se_puede_verificar_pero_restaura(respaldo_exportado):
    preparada = _sesion().preparar_restauracion_clave(respaldo_exportado, PASSWORD)
    assert preparada.verificada is False
    _sesion().aplicar_restauracion_clave(preparada)


@requiere_admin
def test_formato_del_archivo(respaldo_exportado):
    from custodia.core import respaldo

    datos = respaldo_exportado.read_bytes()
    assert len(datos) == respaldo.TAM_ARCHIVO == 88
    assert datos[:8] == b"CUSTKEYB"
    assert datos[8] == 1


# ---------------------------------------------------------------------------
# Fallos que no deben escribir nada
# ---------------------------------------------------------------------------

@requiere_admin
def test_contrasena_incorrecta_no_escribe(respaldo_exportado, clave_maestra):
    from custodia.core.errors import RespaldoError

    antes = _foto(clave_maestra.parent)
    with pytest.raises(RespaldoError, match="Contraseña incorrecta"):
        _sesion().preparar_restauracion_clave(respaldo_exportado, "otra-contrasena-larga")

    assert _foto(clave_maestra.parent) == antes
    fallo = _eventos("restaurar_clave")[0]
    assert fallo["exito"] is False
    assert fallo["detalle"] == "contraseña incorrecta o archivo alterado"


@requiere_admin
@pytest.mark.parametrize("posicion", [12, 20, 36, 60, 87],
                         ids=["scrypt", "sal", "nonce", "cifrado", "etiqueta"])
def test_archivo_alterado_no_escribe(respaldo_exportado, clave_maestra, posicion):
    from custodia.core.errors import RespaldoError

    datos = bytearray(respaldo_exportado.read_bytes())
    datos[posicion] ^= 0x01
    respaldo_exportado.write_bytes(bytes(datos))

    antes = _foto(clave_maestra.parent)
    with pytest.raises(RespaldoError, match="Contraseña incorrecta o archivo alterado"):
        _sesion().preparar_restauracion_clave(respaldo_exportado, PASSWORD)
    assert _foto(clave_maestra.parent) == antes


@requiere_admin
@pytest.mark.parametrize("contenido", [b"", b"x" * 88, b"CUSTKEYB\x02" + b"\0" * 79],
                         ids=["vacio", "otra-magia", "otra-version"])
def test_archivo_que_no_es_respaldo(clave_maestra, raiz, bitacora, tmp_path, contenido):
    from custodia.core.errors import RespaldoError

    falso = tmp_path / "falso.custodiakey"
    falso.write_bytes(contenido)
    with pytest.raises(RespaldoError, match="no es un respaldo"):
        _sesion().preparar_restauracion_clave(falso, PASSWORD)


@requiere_admin
def test_archivo_inexistente(clave_maestra, raiz, bitacora, tmp_path):
    from custodia.core.errors import RespaldoError

    with pytest.raises(RespaldoError, match="No se pudo leer"):
        _sesion().preparar_restauracion_clave(tmp_path / "no-existe", PASSWORD)


@requiere_admin
def test_clave_que_no_abre_el_almacen_se_rechaza(respaldo_exportado, clave_maestra, raiz):
    from custodia.core.errors import RespaldoError

    _cambiar_de_clave()
    _archivo_cifrado(raiz)   # cifrado con una clave que no es la del respaldo

    antes = _foto(clave_maestra.parent)
    with pytest.raises(RespaldoError, match="no abre los archivos"):
        _sesion().preparar_restauracion_clave(respaldo_exportado, PASSWORD)
    assert _foto(clave_maestra.parent) == antes


@requiere_admin
def test_un_archivo_danado_no_impide_recuperar(respaldo_exportado, raiz):
    danado = bytearray(_archivo_cifrado(raiz, "danado.txt").read_bytes())
    danado[-1] ^= 0x01
    (raiz / "danado.txt").write_bytes(bytes(danado))
    _archivo_cifrado(raiz, "sano.txt")

    assert _sesion().preparar_restauracion_clave(respaldo_exportado, PASSWORD).verificada


@requiere_admin
def test_la_verificacion_ignora_lo_que_no_usa_la_clave_maestra(respaldo_exportado, raiz):
    from custodia.core import crypto

    (raiz / "plano.txt").write_bytes(b"archivo sin cifrar")
    (raiz / "boveda.bin").write_bytes(
        crypto.MAGIA + b"\x02" + b"\0" * crypto.TAM_CABECERA)

    assert _sesion().preparar_restauracion_clave(respaldo_exportado, PASSWORD).verificada is False


# ---------------------------------------------------------------------------
# Autorización
# ---------------------------------------------------------------------------

@requiere_admin
def test_no_administrador_no_exporta(clave_maestra, raiz, bitacora, tmp_path):
    destino = tmp_path / "robo.custodiakey"
    with pytest.raises(PermissionError):
        _sesion(es_admin=False).exportar_respaldo_clave(PASSWORD, destino)

    assert not destino.exists()
    denegado = _eventos("exportar_clave")[0]
    assert denegado["exito"] is False and denegado["usuario"] == "usuario_prueba"


@requiere_admin
def test_no_administrador_no_restaura(respaldo_exportado, clave_maestra):
    from custodia.core import respaldo

    antes = _foto(clave_maestra.parent)
    usuario = _sesion(es_admin=False)
    with pytest.raises(PermissionError):
        usuario.preparar_restauracion_clave(respaldo_exportado, PASSWORD)

    preparada = respaldo.preparar(respaldo_exportado, PASSWORD)
    with pytest.raises(PermissionError):
        usuario.aplicar_restauracion_clave(preparada)

    assert _foto(clave_maestra.parent) == antes
    denegados = [e for e in _eventos("restaurar_clave") if not e["exito"]]
    assert len(denegados) == 2


# ---------------------------------------------------------------------------
# La clave y la contraseña no se filtran
# ---------------------------------------------------------------------------

@requiere_admin
def test_la_clave_no_aparece_en_respaldo_ni_bitacora(clave_maestra, raiz, bitacora, tmp_path):
    clave = _clave_actual()
    destino = tmp_path / "respaldo.custodiakey"
    sesion = _sesion()

    sesion.exportar_respaldo_clave(PASSWORD, destino)
    with pytest.raises(Exception):
        sesion.preparar_restauracion_clave(destino, "otra-contrasena-larga")
    sesion.aplicar_restauracion_clave(sesion.preparar_restauracion_clave(destino, PASSWORD))

    from custodia.core import audit
    audit.flush()

    secretos = [clave, clave.hex().encode(), base64.b64encode(clave),
                PASSWORD.encode(), PASSWORD.encode("utf-16-le")]
    for contenido in (destino.read_bytes(), bitacora.read_bytes()):
        for secreto in secretos:
            assert secreto not in contenido


@requiere_admin
def test_restauracion_no_muestra_la_clave(respaldo_exportado):
    from custodia.core import respaldo

    clave = _clave_actual()
    preparada = respaldo.preparar(respaldo_exportado, PASSWORD)
    assert clave.hex() not in repr(preparada)
    assert repr(clave) not in repr(preparada)


# ---------------------------------------------------------------------------
# Reemplazo de la clave
# ---------------------------------------------------------------------------

@requiere_admin
def test_guarda_la_clave_anterior_y_aplica_la_acl(respaldo_exportado, clave_maestra):
    import win32security

    blob_anterior = clave_maestra.read_bytes()
    clave_anterior = _clave_actual()
    _sesion().aplicar_restauracion_clave(
        _sesion().preparar_restauracion_clave(respaldo_exportado, PASSWORD))

    copias = list(clave_maestra.parent.glob("master.key.anterior-*"))
    assert len(copias) == 1
    assert copias[0].read_bytes() == blob_anterior
    assert clave_anterior not in copias[0].read_bytes()
    assert not list(clave_maestra.parent.glob("*.tmp"))

    for ruta in (clave_maestra, copias[0]):
        dacl = win32security.GetNamedSecurityInfo(
            str(ruta), win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION,
        ).GetSecurityDescriptorDacl()
        sids = {win32security.ConvertSidToStringSid(dacl.GetAce(i)[2])
                for i in range(dacl.GetAceCount())}
        assert sids == {"S-1-5-32-544", "S-1-5-18"}


@requiere_admin
def test_fallo_al_instalar_no_cambia_la_clave(respaldo_exportado, clave_maestra, monkeypatch):
    from custodia.core import crypto
    from custodia.core.errors import CryptoError

    def falla(*_):
        raise OSError("disco lleno")

    preparada = _sesion().preparar_restauracion_clave(respaldo_exportado, PASSWORD)
    antes = _foto(clave_maestra.parent)
    monkeypatch.setattr(crypto.os, "replace", falla)

    with pytest.raises(CryptoError):
        _sesion().aplicar_restauracion_clave(preparada)

    assert _foto(clave_maestra.parent) == antes
    assert _eventos("restaurar_clave")[0]["detalle"] == "CryptoError"


@requiere_admin
def test_clave_de_tamano_invalido_no_se_instala(clave_maestra):
    from custodia.core import crypto
    from custodia.core.errors import CryptoError

    with pytest.raises(CryptoError):
        crypto.instalar_clave_maestra(b"corta")


@requiere_admin
def test_purga_solo_copias_vencidas(clave_maestra):
    from custodia.core import crypto

    vieja = clave_maestra.with_name("master.key.anterior-vieja")
    reciente = clave_maestra.with_name("master.key.anterior-reciente")
    vieja.write_bytes(b"x")
    reciente.write_bytes(b"x")
    hace_31_dias = time.time() - 31 * 86400
    os.utime(vieja, (hace_31_dias, hace_31_dias))

    assert crypto.purgar_copias_anteriores(30) == 1
    assert not vieja.exists() and reciente.exists() and clave_maestra.exists()


# ---------------------------------------------------------------------------
# Exportación
# ---------------------------------------------------------------------------

@requiere_admin
def test_contrasena_corta_se_rechaza(clave_maestra, raiz, bitacora, tmp_path):
    from custodia.core.errors import RespaldoError

    destino = tmp_path / "respaldo.custodiakey"
    with pytest.raises(RespaldoError, match="12 caracteres"):
        _sesion().exportar_respaldo_clave("once-letras", destino)
    assert not destino.exists()


@requiere_admin
def test_doce_caracteres_se_aceptan(clave_maestra, raiz, bitacora, tmp_path):
    destino = tmp_path / "respaldo.custodiakey"
    _sesion().exportar_respaldo_clave("doce-letras!", destino)
    assert destino.exists()


@requiere_admin
def test_la_contrasena_se_normaliza(respaldo_exportado, clave_maestra, tmp_path):
    from custodia.core import respaldo

    clave = _clave_actual()
    compuesta = "contraseña-de-respaldo"
    descompuesta = "contraseña-de-respaldo"
    assert respaldo.abrir(respaldo.sellar(clave, compuesta), descompuesta) == clave


@requiere_admin
@pytest.mark.parametrize("lugar", ["almacen", "junto_a_la_clave", "sobre_la_clave"])
def test_destino_prohibido(clave_maestra, raiz, bitacora, lugar):
    from custodia.core.errors import RespaldoError

    destino = {"almacen": raiz / "r.custodiakey",
               "junto_a_la_clave": clave_maestra.with_name("r.custodiakey"),
               "sobre_la_clave": clave_maestra}[lugar]
    antes = clave_maestra.read_bytes()

    with pytest.raises(RespaldoError, match="Elige otro lugar"):
        _sesion().exportar_respaldo_clave(PASSWORD, destino)

    assert clave_maestra.read_bytes() == antes
    assert lugar == "sobre_la_clave" or not destino.exists()


@requiere_admin
def test_destino_que_no_se_puede_escribir(clave_maestra, raiz, bitacora, tmp_path):
    from custodia.core.errors import RespaldoError

    with pytest.raises(RespaldoError, match="No se pudo escribir"):
        _sesion().exportar_respaldo_clave(PASSWORD, tmp_path / "no-existe" / "r.custodiakey")
    fallo = _eventos("exportar_clave")[0]
    assert fallo["detalle"] == "no se pudo escribir el destino"


@requiere_admin
def test_la_escritura_defectuosa_se_detecta(clave_maestra, raiz, bitacora, tmp_path, monkeypatch):
    from pathlib import Path

    from custodia.core.errors import RespaldoError

    leer_real = Path.read_bytes
    monkeypatch.setattr(
        Path, "read_bytes",
        lambda self: b"corrupto" if self.name == "r.custodiakey" else leer_real(self))

    with pytest.raises(RespaldoError, match="con errores"):
        _sesion().exportar_respaldo_clave(PASSWORD, tmp_path / "r.custodiakey")


@requiere_admin
def test_exportar_sin_clave_disponible(clave_maestra, raiz, bitacora, tmp_path):
    from custodia.core import crypto
    from custodia.core.errors import RespaldoError

    clave_maestra.write_bytes(b"blob danado")
    crypto.olvidar_clave()
    with pytest.raises(RespaldoError, match="no está disponible"):
        _sesion().exportar_respaldo_clave(PASSWORD, tmp_path / "r.custodiakey")


@requiere_admin
def test_la_bitacora_registra_exportar_y_restaurar(respaldo_exportado):
    sesion = _sesion()
    sesion.aplicar_restauracion_clave(
        sesion.preparar_restauracion_clave(respaldo_exportado, PASSWORD))

    exportado = _eventos("exportar_clave")[0]
    assert exportado["exito"] and exportado["detalle"] == "archivo: respaldo.custodiakey"
    restaurado = _eventos("restaurar_clave")[0]
    assert restaurado["exito"] and "reemplazó" in restaurado["detalle"]


# ---------------------------------------------------------------------------
# Modo de recuperación
# ---------------------------------------------------------------------------

@requiere_admin
def test_clave_danada_no_impide_arrancar(clave_maestra, raiz, tmp_path, monkeypatch):
    from custodia.core import audit, config, crypto
    from custodia.gui.sesion import arrancar_nucleo, detener_nucleo

    monkeypatch.setattr(config, "AUDIT_DB", tmp_path / "arranque.db")
    clave_maestra.write_bytes(b"blob danado")
    crypto.olvidar_clave()

    arrancar_nucleo()
    try:
        assert not crypto.clave_disponible()
        assert audit.consultar(accion="clave_no_disponible")[0]["exito"] is False
    finally:
        detener_nucleo()


@requiere_admin
def test_no_se_lee_ni_escribe_sin_clave(clave_maestra, raiz, bitacora, monkeypatch):
    from custodia.core import crypto, fsops
    from custodia.core.errors import CryptoError

    archivo = _archivo_cifrado(raiz)
    clave_maestra.write_bytes(b"blob danado")
    crypto.olvidar_clave()
    sesion = _sesion()

    with pytest.raises(CryptoError, match="debe restaurar"):
        sesion.escribir("/nuevo.txt", b"datos")
    assert not (raiz / "nuevo.txt").exists()

    monkeypatch.setattr("custodia.gui.sesion.impersonate", _sin_suplantar)
    monkeypatch.setattr(fsops, "leer", lambda ruta, descifrar: archivo.read_bytes())
    with pytest.raises(CryptoError, match="debe restaurar"):
        sesion.leer("/expediente.txt")


class _sin_suplantar:
    def __init__(self, _token) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


@requiere_admin
def test_clave_perdida_solo_con_archivos_cifrados(clave_maestra, raiz):
    from custodia.core import crypto, respaldo

    assert not respaldo.clave_perdida()     # hay clave

    clave_maestra.unlink()
    crypto.olvidar_clave()
    assert not respaldo.clave_perdida()     # almacén vacío: equipo nuevo

    (raiz / "plano.txt").write_bytes(b"sin cifrar")
    assert not respaldo.clave_perdida()     # nada depende de la clave

    (raiz / "cifrado.bin").write_bytes(crypto.MAGIA + b"\x01" + b"\0" * 40)
    assert respaldo.clave_perdida()
