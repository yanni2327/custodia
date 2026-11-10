# -*- coding: utf-8 -*-
"""
Cifrado por usuario de punta a punta (C20): formato v3, identidades, clave de
recuperación y migración desde v1.

Las pruebas con cuenta real usan LogonUser, suplantación y ACL de verdad, sobre
un almacén, una clave y unas identidades temporales.
"""
from __future__ import annotations

import base64
import json
import struct

import pytest

from conftest import pytestmark, requiere_admin  # noqa: F401

from custodia.core import boveda, config, crypto, migracion, recuperacion, respaldo
from custodia.core.errors import CryptoError, IdentidadAlterada, RespaldoError
from custodia.gui.sesion import Sesion

CLAVE_USB = "clave-de-la-usb-del-dueno"
PASSWORD = "Prueba.2026!SOP"


@pytest.fixture(autouse=True)
def almacen_identidades(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "BOVEDA_FILE", tmp_path / "identidades.json")
    monkeypatch.setattr(boveda, "_SCRYPT_N", 2 ** 12)
    monkeypatch.setattr(boveda.crypto, "proteger_solo_admin", lambda ruta: None)


@pytest.fixture
def usb(tmp_path, monkeypatch):
    """Equipo con clave de recuperación creada y C20 encendido."""
    monkeypatch.setattr(config, "CIFRADO_POR_USUARIO", True)
    destino = tmp_path / "usb" / "clave.custodiarec"
    destino.parent.mkdir()
    recuperacion.crear(CLAVE_USB, destino)
    return destino


def _store() -> dict:
    return json.loads(config.BOVEDA_FILE.read_text("utf-8"))


def _guardar(datos: dict) -> None:
    config.BOVEDA_FILE.write_text(json.dumps(datos), "utf-8")


# ---------------------------------------------------------------------------
# Formato v3
# ---------------------------------------------------------------------------

def test_cabecera_autenticada_impide_anadir_un_destinatario():
    ana, intruso = boveda.generar_par(), boveda.generar_par()
    blob = boveda.cifrar(b"secreto", {"ana": ana.public_key()})
    _, tam, nonce, sobres, cuerpo, _ = boveda._desarmar(blob)
    sobres["intruso"] = intruso.public_key().encrypt(b"x" * 32, boveda._OAEP)

    alterado = boveda._armar_cabecera(tam, nonce, sobres) + cuerpo

    with pytest.raises(CryptoError):
        boveda.descifrar(alterado, "ana", ana)


def test_actualizar_rechaza_una_cabecera_alterada():
    """El ataque: que el siguiente guardado cifre también para el intruso."""
    ana, intruso = boveda.generar_par(), boveda.generar_par()
    blob = boveda.cifrar(b"secreto", {"ana": ana.public_key()})
    _, tam, nonce, sobres, cuerpo, _ = boveda._desarmar(blob)
    sobres["intruso"] = intruso.public_key().encrypt(b"x" * 32, boveda._OAEP)
    alterado = boveda._armar_cabecera(tam, nonce, sobres) + cuerpo

    with pytest.raises(CryptoError):
        boveda.actualizar(alterado, b"nuevo", "ana", ana)


def test_actualizar_conserva_a_los_destinatarios():
    ana, bob = boveda.generar_par(), boveda.generar_par()
    blob = boveda.cifrar(b"v1", {"ana": ana.public_key(), "bob": bob.public_key()})

    nuevo = boveda.actualizar(blob, b"contenido nuevo", "ana", ana)

    assert boveda.descifrar(nuevo, "bob", bob) == b"contenido nuevo"
    assert boveda._desarmar(nuevo)[2] != boveda._desarmar(blob)[2]   # nonce nuevo


def test_el_cuerpo_alterado_se_detecta():
    ana = boveda.generar_par()
    blob = bytearray(boveda.cifrar(b"secreto", {"ana": ana.public_key()}))
    blob[-1] ^= 1
    with pytest.raises(CryptoError):
        boveda.descifrar(bytes(blob), "ana", ana)


def test_cabecera_truncada_da_error_del_dominio():
    blob = crypto.MAGIA + bytes([boveda.VERSION]) + b"\0" * 20 + struct.pack(">H", 5)
    with pytest.raises(CryptoError):
        boveda.destinatarios(blob)


def test_se_siguen_leyendo_los_v2():
    ana = boveda.generar_par()
    dek = b"k" * 32
    nonce = b"n" * 12
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    sobre = ana.public_key().encrypt(dek, boveda._OAEP)
    cabecera = crypto._CABECERA.pack(crypto.MAGIA, 2, 4) + nonce + struct.pack(">H", 1)
    cabecera += bytes([3]) + b"ana" + struct.pack(">H", len(sobre)) + sobre
    v2 = cabecera + AESGCM(dek).encrypt(nonce, b"hola", None)

    assert boveda.es_v2(v2)
    assert boveda.descifrar(v2, "ana", ana) == b"hola"
    assert not boveda.es_v2(boveda.actualizar(v2, b"hola", "ana", ana))


def test_el_sobre_de_recuperacion_no_cuenta_como_persona():
    ana, rec = boveda.generar_par(), boveda.generar_par()
    blob = boveda.cifrar(b"x", {"ana": ana.public_key()}, recuperacion=rec.public_key())

    assert boveda.destinatarios(blob) == ["ana"]
    assert boveda.tiene_sobre_de_recuperacion(blob)


def test_el_nombre_reservado_no_puede_ser_una_cuenta_de_windows():
    assert "*" in boveda.RECUPERACION


# ---------------------------------------------------------------------------
# Identidades
# ---------------------------------------------------------------------------

def test_un_almacen_danado_no_se_pisa():
    config.BOVEDA_FILE.write_text("{dañado", "utf-8")

    with pytest.raises(CryptoError):
        boveda.crear_identidad("ana", "secreta")

    assert config.BOVEDA_FILE.read_text("utf-8") == "{dañado"


def test_activo_exige_la_opcion_y_la_clave_de_recuperacion(monkeypatch, tmp_path):
    assert not boveda.activo()

    monkeypatch.setattr(config, "CIFRADO_POR_USUARIO", True)
    assert not boveda.activo()

    boveda.configurar_recuperacion(boveda.generar_par().public_key())
    assert boveda.activo()


def test_con_almacen_danado_sigue_activo_para_fallar_cerrado(monkeypatch):
    monkeypatch.setattr(config, "CIFRADO_POR_USUARIO", True)
    config.BOVEDA_FILE.write_text("{dañado", "utf-8")
    assert boveda.activo()


def test_la_recuperacion_solo_se_configura_una_vez():
    boveda.configurar_recuperacion(boveda.generar_par().public_key())
    with pytest.raises(CryptoError):
        boveda.configurar_recuperacion(boveda.generar_par().public_key())


def test_cifrar_para_exige_clave_de_recuperacion():
    ana = boveda.generar_par()
    with pytest.raises(CryptoError):
        boveda.cifrar_para(b"x", {"ana": ana.public_key()})


def test_identidad_nueva_y_reapertura():
    boveda.configurar_recuperacion(boveda.generar_par().public_key())

    privada, regenerada = boveda.abrir_o_crear_identidad("Ana", "secreta")
    otra, otra_vez = boveda.abrir_o_crear_identidad("ana", "secreta")

    assert not regenerada and not otra_vez
    assert boveda.huella(privada) == boveda.huella(otra)
    assert not boveda.pendiente_recuperacion("ana")


def test_contrasena_distinta_regenera_y_queda_pendiente():
    boveda.configurar_recuperacion(boveda.generar_par().public_key())
    vieja, _ = boveda.abrir_o_crear_identidad("ana", "secreta")

    nueva, regenerada = boveda.abrir_o_crear_identidad("ana", "otra-clave")

    assert regenerada and boveda.pendiente_recuperacion("ana")
    assert boveda.huella(nueva) != boveda.huella(vieja)


def test_sustituir_la_publica_se_detecta_al_entrar():
    boveda.configurar_recuperacion(boveda.generar_par().public_key())
    boveda.abrir_o_crear_identidad("ana", "secreta")
    atacante = boveda.generar_par()
    store = _store()
    store["ana"]["publica"] = base64.b64encode(boveda.publica_a_bytes(atacante)).decode()
    _guardar(store)

    with pytest.raises(IdentidadAlterada):
        boveda.abrir_o_crear_identidad("ana", "secreta")


def test_sustituir_la_clave_de_recuperacion_se_detecta_al_entrar():
    boveda.configurar_recuperacion(boveda.generar_par().public_key())
    boveda.abrir_o_crear_identidad("ana", "secreta")
    atacante = boveda.generar_par()
    store = _store()
    store[boveda.RECUPERACION] = {
        "publica": base64.b64encode(boveda.publica_a_bytes(atacante)).decode(),
        "huella": boveda.huella(atacante),
    }
    _guardar(store)

    with pytest.raises(IdentidadAlterada):
        boveda.abrir_o_crear_identidad("ana", "secreta")
    assert not boveda.pendiente_recuperacion("ana")


def test_una_identidad_antigua_se_actualiza_al_entrar():
    boveda.configurar_recuperacion(boveda.generar_par().public_key())
    privada = boveda.generar_par()
    blob, sal = boveda.envolver_privada(privada, "secreta", n=boveda._SCRYPT_N_ANTERIOR)
    store = _store()
    store["ana"] = {
        "publica": base64.b64encode(boveda.publica_a_bytes(privada)).decode(),
        "privada": base64.b64encode(blob).decode(),
        "sal": base64.b64encode(sal).decode(),
    }
    _guardar(store)

    abierta, regenerada = boveda.abrir_o_crear_identidad("ana", "secreta")

    assert not regenerada and boveda.huella(abierta) == boveda.huella(privada)
    assert _store()["ana"]["v"] == boveda.VERSION
    assert _store()["ana"]["huella_rec"] == boveda.huella_recuperacion()


def test_cambiar_contrasena_conserva_la_identidad():
    boveda.configurar_recuperacion(boveda.generar_par().public_key())
    original, _ = boveda.abrir_o_crear_identidad("ana", "vieja")

    assert boveda.cambiar_contrasena("ana", "vieja", "nueva")

    assert boveda.cargar_privada("ana", "vieja") is None
    assert boveda.huella(boveda.cargar_privada("ana", "nueva")) == boveda.huella(original)
    assert not boveda.cambiar_contrasena("ana", "equivocada", "x")


def test_cada_identidad_guarda_su_coste_de_scrypt():
    boveda.crear_identidad("ana", "secreta")
    assert _store()["ana"]["n"] == boveda._SCRYPT_N


# ---------------------------------------------------------------------------
# Clave de recuperación en la USB
# ---------------------------------------------------------------------------

def test_la_privada_no_queda_en_el_equipo(usb):
    assert usb.exists()
    almacen = config.BOVEDA_FILE.read_bytes()
    assert b"PRIVATE" not in almacen and b'"privada"' not in almacen
    assert boveda.recuperacion_configurada()


def test_abrir_la_usb(usb):
    clave = recuperacion.abrir(usb, CLAVE_USB)
    assert boveda.huella(clave._privada) == boveda.huella_recuperacion()
    assert "oculta" in repr(clave)


def test_contrasena_equivocada(usb):
    with pytest.raises(RespaldoError, match="Contraseña incorrecta"):
        recuperacion.abrir(usb, "otra-contrasena-larga")


def test_archivo_alterado(usb):
    datos = bytearray(usb.read_bytes())
    datos[-1] ^= 1
    usb.write_bytes(bytes(datos))
    with pytest.raises(RespaldoError, match="alterado"):
        recuperacion.abrir(usb, CLAVE_USB)


def test_archivo_que_no_es_una_clave(usb, tmp_path):
    falso = tmp_path / "falso.custodiarec"
    falso.write_bytes(b"x" * 200)
    with pytest.raises(RespaldoError, match="no es un respaldo"):
        recuperacion.abrir(falso, CLAVE_USB)
    grande = tmp_path / "grande.custodiarec"
    grande.write_bytes(b"x" * 20000)
    with pytest.raises(RespaldoError, match="no es una clave"):
        recuperacion.abrir(grande, CLAVE_USB)
    with pytest.raises(RespaldoError, match="No se pudo leer"):
        recuperacion.abrir(tmp_path / "no-existe", CLAVE_USB)


def test_una_usb_de_otro_equipo_se_rechaza(usb):
    store = _store()
    otra = boveda.generar_par()
    store[boveda.RECUPERACION] = {
        "publica": base64.b64encode(boveda.publica_a_bytes(otra)).decode(),
        "huella": boveda.huella(otra),
    }
    _guardar(store)
    with pytest.raises(RespaldoError, match="no corresponde"):
        recuperacion.abrir(usb, CLAVE_USB)


def test_no_se_crea_una_segunda_clave(usb, tmp_path):
    with pytest.raises(RespaldoError, match="ya tiene"):
        recuperacion.crear(CLAVE_USB, tmp_path / "otra.custodiarec")


def test_contrasena_corta_y_destino_prohibido(tmp_path, monkeypatch):
    with pytest.raises(RespaldoError, match="12 caracteres"):
        recuperacion.crear("corta", tmp_path / "x.custodiarec")

    almacen = tmp_path / "almacen"
    almacen.mkdir()
    monkeypatch.setattr(config, "STORAGE_ROOT", almacen)
    with pytest.raises(RespaldoError, match="Elige otro lugar"):
        recuperacion.crear(CLAVE_USB, almacen / "x.custodiarec")
    assert not boveda.recuperacion_configurada()


def test_si_la_usb_falla_no_se_registra_la_clave(tmp_path):
    with pytest.raises(RespaldoError, match="No se pudo escribir"):
        recuperacion.crear(CLAVE_USB, tmp_path / "no-existe" / "x.custodiarec")
    assert not boveda.recuperacion_configurada()


# ---------------------------------------------------------------------------
# Respaldo de identidades
# ---------------------------------------------------------------------------

@requiere_admin
def test_el_respaldo_incluye_las_identidades(clave_maestra, raiz, bitacora, tmp_path):
    boveda.crear_identidad("ana", "secreta")
    destino = tmp_path / "r.custodiakey"

    respaldo.exportar(CLAVE_USB, destino)

    copia = destino.with_name("r.custodiakey.identidades")
    assert b"ana" not in copia.read_bytes()

    config.BOVEDA_FILE.unlink()
    respaldo.aplicar(respaldo.preparar(destino, CLAVE_USB))
    assert boveda.cargar_privada("ana", "secreta") is not None


@requiere_admin
def test_restaurar_no_pisa_identidades_existentes(clave_maestra, raiz, bitacora, tmp_path):
    boveda.crear_identidad("ana", "secreta")
    destino = tmp_path / "r.custodiakey"
    respaldo.exportar(CLAVE_USB, destino)
    boveda.crear_identidad("ana", "mas-reciente")
    boveda.crear_identidad("luis", "suya")

    respaldo.aplicar(respaldo.preparar(destino, CLAVE_USB))

    assert boveda.cargar_privada("ana", "mas-reciente") is not None
    assert boveda.tiene_identidad("luis")


@requiere_admin
def test_copia_de_identidades_alterada_no_escribe_nada(clave_maestra, raiz, bitacora, tmp_path):
    boveda.crear_identidad("ana", "secreta")
    destino = tmp_path / "r.custodiakey"
    respaldo.exportar(CLAVE_USB, destino)
    copia = destino.with_name("r.custodiakey.identidades")
    datos = bytearray(copia.read_bytes())
    datos[-1] ^= 1
    copia.write_bytes(bytes(datos))
    blob = clave_maestra.read_bytes()

    with pytest.raises(RespaldoError):
        respaldo.preparar(destino, CLAVE_USB)

    assert clave_maestra.read_bytes() == blob


@requiere_admin
def test_sin_identidades_no_se_escribe_la_copia(clave_maestra, raiz, bitacora, tmp_path):
    destino = tmp_path / "r.custodiakey"
    respaldo.exportar(CLAVE_USB, destino)
    assert not destino.with_name("r.custodiakey.identidades").exists()


# ---------------------------------------------------------------------------
# De punta a punta, con una cuenta real de Windows
# ---------------------------------------------------------------------------

@pytest.fixture
def entorno(raiz, usuario_prueba, clave_maestra, bitacora, tmp_path, monkeypatch, usb):
    """Almacén con carpeta compartida y archivos de sesión aislados."""
    from custodia.core import espacios

    monkeypatch.setattr(config, "STORAGE_ROOT", raiz.resolve())
    monkeypatch.setattr(config, "SEGUNDO_FACTOR_FILE", tmp_path / "2fa.dat")
    monkeypatch.setattr(config, "INTENTOS_FILE", tmp_path / "intentos.dat")
    espacios.preparar_compartida()
    cuenta, password = usuario_prueba
    return cuenta.username, password, raiz.resolve()


@pytest.fixture
def sesion(entorno):
    usuario, password, _ = entorno
    s = Sesion.iniciar(usuario, password)
    yield s
    s.token.Close()


def _version(ruta) -> int:
    return ruta.read_bytes()[len(crypto.MAGIA)]


def _v1(ruta, contenido: bytes) -> None:
    ruta.write_bytes(crypto.cifrar(contenido))


@requiere_admin
def test_entrar_crea_la_identidad(sesion, entorno):
    assert sesion.privada is not None
    assert boveda.tiene_identidad(entorno[0])


@requiere_admin
def test_escribir_y_leer_en_v3_con_sobre_de_recuperacion(sesion, entorno):
    usuario, _, raiz = entorno
    sesion.escribir(f"/{usuario}/a.txt", b"privado")

    blob = (raiz / usuario / "a.txt").read_bytes()
    assert blob[len(crypto.MAGIA)] == boveda.VERSION
    assert boveda.tiene_sobre_de_recuperacion(blob)
    assert sesion.leer(f"/{usuario}/a.txt") == b"privado"


@requiere_admin
def test_sobrescribir_conserva_el_formato(sesion, entorno):
    usuario, _, raiz = entorno
    sesion.escribir(f"/{usuario}/a.txt", b"uno")
    sesion.escribir(f"/{usuario}/a.txt", b"dos", sobrescribir=True)

    assert sesion.leer(f"/{usuario}/a.txt") == b"dos"
    assert boveda.destinatarios((raiz / usuario / "a.txt").read_bytes()) == [usuario.lower()]


@requiere_admin
def test_sin_clave_privada_no_se_degrada_a_v1(sesion, entorno):
    usuario, _, raiz = entorno
    sesion.escribir(f"/{usuario}/a.txt", b"original")
    antes = (raiz / usuario / "a.txt").read_bytes()
    sesion.privada = None

    with pytest.raises(CryptoError, match="no está disponible"):
        sesion.escribir(f"/{usuario}/a.txt", b"nuevo", sobrescribir=True)
    with pytest.raises(CryptoError, match="no está disponible"):
        sesion.escribir(f"/{usuario}/b.txt", b"nuevo")
    with pytest.raises(CryptoError, match="no está disponible"):
        sesion.leer(f"/{usuario}/a.txt")

    assert (raiz / usuario / "a.txt").read_bytes() == antes
    assert not (raiz / usuario / "b.txt").exists()


@requiere_admin
def test_la_carpeta_compartida_sigue_en_v1(sesion, entorno):
    _, _, raiz = entorno
    sesion.escribir("/Compartida/comun.txt", b"para todos")

    assert _version(raiz / "Compartida" / "comun.txt") == crypto.VERSION
    assert sesion.leer("/Compartida/comun.txt") == b"para todos"


def _sin_temporales(carpeta) -> bool:
    return not list(carpeta.glob(".*.tmp"))


@requiere_admin
def test_un_usuario_normal_guarda_y_gestiona_lo_suyo_en_compartida(sesion, entorno):
    """Con los permisos reales de la carpeta, sin nada añadido por la prueba."""
    _, _, raiz = entorno
    carpeta = raiz / "Compartida"

    sesion.escribir("/Compartida/mio.txt", b"uno")
    sesion.escribir("/Compartida/mio.txt", b"dos", sobrescribir=True)
    assert sesion.leer("/Compartida/mio.txt") == b"dos"

    sesion.renombrar("/Compartida/mio.txt", "nuevo.txt")
    sesion.eliminar("/Compartida/nuevo.txt")

    assert not (carpeta / "nuevo.txt").exists() and _sin_temporales(carpeta)


@pytest.fixture
def otra_sesion(entorno):
    """Segunda cuenta real del grupo de usuarios."""
    from custodia.core import accounts, auth

    nombre = "cust_t2"
    try:
        accounts.eliminar_usuario(nombre)
    except Exception:
        pass
    accounts.crear_usuario(nombre, PASSWORD)
    token = auth.logon(nombre, PASSWORD)
    yield Sesion(username=nombre, token=token, es_admin=False)
    token.Close()
    accounts.eliminar_usuario(nombre)


@requiere_admin
def test_en_compartida_nadie_toca_lo_de_otro(sesion, otra_sesion, entorno):
    from custodia.core.errors import PermissionDenied

    _, _, raiz = entorno
    carpeta = raiz / "Compartida"
    sesion.escribir("/Compartida/suyo.txt", b"original")

    assert otra_sesion.leer("/Compartida/suyo.txt") == b"original"
    with pytest.raises(PermissionDenied):
        otra_sesion.escribir("/Compartida/suyo.txt", b"pisado", sobrescribir=True)
    with pytest.raises(PermissionDenied):
        otra_sesion.eliminar("/Compartida/suyo.txt")

    assert sesion.leer("/Compartida/suyo.txt") == b"original"
    assert _sin_temporales(carpeta)


def _compartida_antigua(raiz):
    """La carpeta como la dejaba la versión anterior, sin el permiso del creador."""
    from custodia.core import acl
    from custodia.core.acl import Perm

    carpeta = raiz / "Compartida"
    carpeta.mkdir(exist_ok=True)
    acl.establecer_permisos(carpeta, [
        ("Administrators", int(Perm.TOTAL), True, True),
        (config.APP_GROUP, int(Perm.LEER), True, True),
    ], romper_herencia=True)
    return carpeta


@requiere_admin
def test_actualizar_compartida_solo_anade_lo_que_falta(raiz, grupos_app, monkeypatch):
    from custodia.core import acl, espacios

    monkeypatch.setattr(config, "STORAGE_ROOT", raiz.resolve())
    carpeta = _compartida_antigua(raiz)
    antes = {e.sid for e in acl.leer_permisos(carpeta)}

    espacios.actualizar_compartida()
    primera = acl.leer_permisos(carpeta)
    espacios.actualizar_compartida()

    entradas = acl.leer_permisos(carpeta)
    assert antes <= {e.sid for e in entradas}, "se perdió un permiso existente"
    assert len(entradas) == len(primera), "no es idempotente"
    assert sum(e.sid == "S-1-3-0" for e in entradas) == 1
    assert not any(e.heredado for e in entradas), "la herencia debe seguir rota"


def test_actualizar_sin_carpeta_no_hace_nada(tmp_path, monkeypatch):
    from custodia.core import espacios

    monkeypatch.setattr(config, "STORAGE_ROOT", tmp_path)
    espacios.actualizar_compartida()
    assert not (tmp_path / "Compartida").exists()


@requiere_admin
def test_el_arranque_corrige_una_compartida_antigua(raiz, clave_maestra, grupos_app,
                                                    tmp_path, monkeypatch):
    from custodia.core import acl
    from custodia.gui.sesion import arrancar_nucleo, detener_nucleo

    monkeypatch.setattr(config, "STORAGE_ROOT", raiz.resolve())
    monkeypatch.setattr(config, "AUDIT_DB", tmp_path / "arranque.db")
    carpeta = _compartida_antigua(raiz)

    arrancar_nucleo()
    detener_nucleo()

    assert any(e.sid == "S-1-3-0" for e in acl.leer_permisos(carpeta))


@requiere_admin
def test_quien_no_es_destinatario_no_puede_leer(sesion, entorno):
    """El objetivo de C20: otra identidad, con NTFS a favor, no abre el archivo."""
    usuario, _, raiz = entorno
    sesion.escribir(f"/{usuario}/a.txt", b"privado")
    blob = (raiz / usuario / "a.txt").read_bytes()

    with pytest.raises(CryptoError, match="destinatarios"):
        boveda.descifrar(blob, "administrador", boveda.generar_par())


@requiere_admin
def test_compartir_un_archivo_con_otra_persona(sesion, entorno):
    usuario, _, raiz = entorno
    boveda.crear_identidad("bob", "suya")
    sesion.escribir(f"/{usuario}/a.txt", b"nomina")

    sesion.compartir(f"/{usuario}/a.txt", "bob")

    privada_bob = boveda.cargar_privada("bob", "suya")
    assert boveda.descifrar((raiz / usuario / "a.txt").read_bytes(), "bob",
                            privada_bob) == b"nomina"


@requiere_admin
def test_cambiar_de_contrasena_en_la_aplicacion_no_pierde_nada(entorno):
    usuario, password, _ = entorno
    s = Sesion.iniciar(usuario, password)
    s.escribir(f"/{usuario}/a.txt", b"privado")
    s.cambiar_mi_contrasena(password, "Nueva.2026!SOP")
    s.token.Close()

    otra = Sesion.iniciar(usuario, "Nueva.2026!SOP")
    assert otra.leer(f"/{usuario}/a.txt") == b"privado"
    otra.token.Close()


@requiere_admin
def test_identidad_alterada_falla_cerrado_sin_impedir_entrar(entorno):
    from custodia.core import audit

    usuario, password, _ = entorno
    Sesion.iniciar(usuario, password).token.Close()
    store = _store()
    store[usuario.lower()]["publica"] = base64.b64encode(
        boveda.publica_a_bytes(boveda.generar_par())).decode()
    _guardar(store)

    s = Sesion.iniciar(usuario, password)

    assert s.privada is None
    audit.flush()
    assert audit.consultar(accion="identidad_no_disponible")[0]["detalle"] == "IdentidadAlterada"
    s.token.Close()


@requiere_admin
def test_perder_la_contrasena_y_recuperar_con_la_usb(entorno, usb, usuario_prueba, grupos_app):
    """El ciclo completo: restablecer, perder el acceso, y recuperarlo con la USB."""
    from custodia.core import accounts, audit

    usuario, password, raiz = entorno
    primera = Sesion.iniciar(usuario, password)
    primera.escribir(f"/{usuario}/a.txt", b"irremplazable")
    primera.token.Close()

    # Un administrador la restablece, como cuando alguien la olvidó.
    accounts.cambiar_password(usuario, "Otra.2026!SOP")

    segunda = Sesion.iniciar(usuario, "Otra.2026!SOP")
    assert boveda.pendiente_recuperacion(usuario)
    with pytest.raises(CryptoError):
        segunda.leer(f"/{usuario}/a.txt")

    administrador = Sesion(username="admin", token=segunda.token, es_admin=True)
    clave = administrador.abrir_clave_recuperacion(usb, CLAVE_USB)
    resumen = administrador.recuperar_cuenta(clave, usuario)

    assert (resumen.recuperados, resumen.fallidos) == (1, 0)
    assert not boveda.pendiente_recuperacion(usuario)
    assert segunda.leer(f"/{usuario}/a.txt") == b"irremplazable"
    audit.flush()
    assert audit.consultar(accion="identidad_regenerada")
    assert audit.consultar(accion="recuperar_cuenta")[0]["exito"]
    segunda.token.Close()


@requiere_admin
def test_no_se_recupera_una_cuenta_que_no_lo_necesita(sesion, entorno, usb):
    administrador = Sesion(username="admin", token=sesion.token, es_admin=True)
    clave = administrador.abrir_clave_recuperacion(usb, CLAVE_USB)
    with pytest.raises(RespaldoError, match="nada que recuperar"):
        administrador.recuperar_cuenta(clave, entorno[0])


def test_solo_un_administrador_usa_la_clave_de_recuperacion(bitacora, usb, tmp_path):
    from custodia.core import audit

    usuario = Sesion(username="juan", token=None, es_admin=False)
    with pytest.raises(PermissionError):
        usuario.crear_clave_recuperacion(CLAVE_USB, tmp_path / "x.custodiarec")
    with pytest.raises(PermissionError):
        usuario.abrir_clave_recuperacion(usb, CLAVE_USB)
    with pytest.raises(PermissionError):
        usuario.recuperar_cuenta(None, "ana")
    audit.flush()
    assert len(audit.consultar(accion="recuperar_cuenta")) == 2


def test_la_contrasena_de_la_usb_no_va_a_la_bitacora(bitacora, tmp_path, monkeypatch):
    from custodia.core import audit

    monkeypatch.setattr(config, "CIFRADO_POR_USUARIO", True)
    destino = tmp_path / "x.custodiarec"
    admin = Sesion(username="ana", token=None, es_admin=True)
    admin.crear_clave_recuperacion(CLAVE_USB, destino)
    with pytest.raises(RespaldoError):
        admin.abrir_clave_recuperacion(destino, "contrasena-equivocada-larga")

    audit.flush()
    contenido = bitacora.read_bytes()
    assert CLAVE_USB.encode() not in contenido
    assert b"contrasena-equivocada-larga" not in contenido


# ---------------------------------------------------------------------------
# Migración
# ---------------------------------------------------------------------------

@requiere_admin
def test_entrar_migra_la_carpeta_personal(entorno):
    from custodia.core import audit

    usuario, password, raiz = entorno
    _v1(raiz / usuario / "viejo.txt", b"de antes")
    (raiz / usuario / "sub").mkdir()
    _v1(raiz / usuario / "sub" / "otro.txt", b"tambien")

    s = Sesion.iniciar(usuario, password)

    assert _version(raiz / usuario / "viejo.txt") == boveda.VERSION
    assert s.leer(f"/{usuario}/viejo.txt") == b"de antes"
    assert s.leer(f"/{usuario}/sub/otro.txt") == b"tambien"
    audit.flush()
    assert audit.consultar(accion="migracion_cifrado")[0]["detalle"].startswith("2 migrados")
    s.token.Close()


@requiere_admin
def test_migrar_conserva_los_permisos(entorno):
    from custodia.core import acl
    from custodia.core.acl import Perm

    usuario, password, raiz = entorno
    archivo = raiz / usuario / "viejo.txt"
    _v1(archivo, b"de antes")
    acl.conceder(archivo, "Administrators", Perm.LEER, hereda_a_hijos=False)

    Sesion.iniciar(usuario, password).token.Close()

    assert _version(archivo) == boveda.VERSION
    assert any(not e.heredado for e in acl.leer_permisos(archivo))


@requiere_admin
def test_no_se_migra_si_alguien_perderia_el_acceso(entorno, monkeypatch):
    """Un grupo con lectura seguiría teniendo NTFS, pero ya no podría descifrar."""
    from custodia.core import acl
    from custodia.core.acl import Perm

    usuario, password, raiz = entorno
    archivo = raiz / usuario / "con_grupo.txt"
    _v1(archivo, b"de antes")
    acl.conceder(archivo, "Users", Perm.LEER, hereda_a_hijos=False)

    Sesion.iniciar(usuario, password).token.Close()

    assert _version(archivo) == crypto.VERSION


@requiere_admin
def test_un_lector_sin_identidad_retrasa_la_migracion(entorno, monkeypatch):
    from custodia.core import acl, accounts
    from custodia.core.acl import Perm
    import win32net
    import win32netcon

    usuario, password, raiz = entorno
    archivo = raiz / usuario / "para_otro.txt"
    _v1(archivo, b"de antes")
    nombre = "cust_lect"
    try:
        win32net.NetUserDel(None, nombre)
    except Exception:
        pass
    win32net.NetUserAdd(None, 1, {
        "name": nombre, "password": PASSWORD, "priv": win32netcon.USER_PRIV_USER,
        "home_dir": None, "comment": "", "flags": win32netcon.UF_SCRIPT, "script_path": None,
    })
    try:
        acl.conceder(archivo, nombre, Perm.LEER, hereda_a_hijos=False)

        Sesion.iniciar(usuario, password).token.Close()
        assert _version(archivo) == crypto.VERSION

        boveda.crear_identidad(nombre, "suya")
        Sesion.iniciar(usuario, password).token.Close()
        assert _version(archivo) == boveda.VERSION
        assert boveda.descifrar(archivo.read_bytes(), nombre,
                                boveda.cargar_privada(nombre, "suya")) == b"de antes"
    finally:
        win32net.NetUserDel(None, nombre)


@requiere_admin
def test_limite_de_archivos_por_ingreso(sesion, entorno):
    usuario, _, raiz = entorno
    for i in range(4):
        _v1(raiz / usuario / f"{i}.txt", b"x")

    resumen = migracion.migrar_espacio(usuario, sesion.token, sesion.privada, limite=1)

    assert (resumen.migrados, resumen.pendientes) == (1, 3)


@requiere_admin
def test_un_archivo_danado_no_detiene_la_migracion(sesion, entorno):
    usuario, _, raiz = entorno
    malo = bytearray(crypto.cifrar(b"x"))
    malo[-1] ^= 1
    (raiz / usuario / "malo.txt").write_bytes(bytes(malo))
    _v1(raiz / usuario / "bueno.txt", b"y")

    resumen = migracion.migrar_espacio(usuario, sesion.token, sesion.privada)

    assert (resumen.migrados, resumen.fallidos) == (1, 1)
    assert (raiz / usuario / "malo.txt").read_bytes() == bytes(malo)


@requiere_admin
def test_migra_los_v2_que_le_pertenecen(sesion, entorno):
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    usuario, _, raiz = entorno
    dek, nonce = b"k" * 32, b"n" * 12
    sobre = sesion.privada.public_key().encrypt(dek, boveda._OAEP)
    u = usuario.lower().encode()
    cabecera = crypto._CABECERA.pack(crypto.MAGIA, 2, 4) + nonce + struct.pack(">H", 1)
    cabecera += bytes([len(u)]) + u + struct.pack(">H", len(sobre)) + sobre
    archivo = raiz / usuario / "v2.bin"
    archivo.write_bytes(cabecera + AESGCM(dek).encrypt(nonce, b"hola", None))

    assert migracion.migrar_espacio(usuario, sesion.token, sesion.privada).migrados == 1
    assert boveda.tiene_sobre_de_recuperacion(archivo.read_bytes())
    assert sesion.leer(f"/{usuario}/v2.bin") == b"hola"


@requiere_admin
def test_pendientes_ignora_compartida_y_lo_ya_migrado(sesion, entorno):
    usuario, _, raiz = entorno
    _v1(raiz / "Compartida" / "comun.txt", b"x")
    assert migracion.pendientes_fuera_de_compartida() == 0

    _v1(raiz / usuario / "viejo.txt", b"x")
    (raiz / usuario / "claro.txt").write_bytes(b"sin cifrar")
    assert migracion.pendientes_fuera_de_compartida() == 1

    migracion.migrar_espacio(usuario, sesion.token, sesion.privada)
    assert migracion.pendientes_fuera_de_compartida() == 0


def test_por_defecto_sigue_desactivado():
    assert config.CIFRADO_POR_USUARIO is False
    assert not boveda.activo()
