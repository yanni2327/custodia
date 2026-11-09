# -*- coding: utf-8 -*-
"""
Operaciones sobre archivos reales, bajo suplantación real.

Todas corren con el token de una cuenta temporal de Windows: si Windows niega
algo, la prueba lo ve igual que lo vería la aplicación.
"""
from __future__ import annotations

import win32api

import pytest

from conftest import pytestmark, requiere_admin  # noqa: F401


@pytest.fixture
def area(raiz, usuario_prueba, clave_maestra, bitacora):
    """Carpeta donde la cuenta de prueba tiene control total, y su token."""
    from custodia.core import acl, auth
    from custodia.core.acl import Perm

    cuenta, password = usuario_prueba
    carpeta = raiz / "area"
    carpeta.mkdir()
    acl.conceder(raiz, cuenta.username, Perm.TOTAL, hereda_a_hijos=True)

    token = auth.logon(cuenta.username, password)
    yield carpeta, token
    token.Close()


def _vetar(ruta) -> None:
    """Deja el elemento solo para administradores y quien corre la prueba."""
    from custodia.core import acl
    from custodia.core.acl import Perm

    acl.establecer_permisos(
        ruta,
        [("Administrators", int(Perm.TOTAL), True, True),
         (win32api.GetUserName(), int(Perm.TOTAL), True, True)],
        romper_herencia=True,
    )


def _sin_temporales(carpeta) -> bool:
    return not list(carpeta.glob(".*.tmp"))


# ---------------------------------------------------------------------------
# Listar y consultar
# ---------------------------------------------------------------------------

@requiere_admin
def test_listar_ordena_y_muestra_el_cifrado(area):
    from custodia.core import fsops
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    with impersonate(token):
        fsops.escribir(carpeta / "zeta.txt", b"12345")
        fsops.escribir(carpeta / "Alfa.txt", b"hola")
        fsops.crear_carpeta(carpeta / "subcarpeta")

        nodos = fsops.listar(carpeta)

    assert [n.nombre for n in nodos] == ["subcarpeta", "Alfa.txt", "zeta.txt"]
    assert nodos[0].es_carpeta and nodos[0].tamano == 0
    assert nodos[2].cifrado and nodos[2].tamano_claro == 5
    assert nodos[2].tamano > 5


@requiere_admin
def test_listar_con_propietario(area):
    from custodia.core import fsops
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    with impersonate(token):
        fsops.escribir(carpeta / "a.txt", b"x")
        nodo, = fsops.listar(carpeta, con_propietario=True)

    assert nodo.propietario


@requiere_admin
def test_listar_lo_que_no_es_carpeta(area):
    from custodia.core import fsops
    from custodia.core.errors import NotFound
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    with impersonate(token):
        fsops.escribir(carpeta / "a.txt", b"x")
        with pytest.raises(NotFound, match="no es una carpeta"):
            fsops.listar(carpeta / "a.txt")
        with pytest.raises(NotFound, match="No existe"):
            fsops.listar(carpeta / "fantasma")


@requiere_admin
def test_info_incluye_propietario_y_tamano_real(area):
    from custodia.core import fsops
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    with impersonate(token):
        fsops.escribir(carpeta / "a.txt", b"contenido")
        nodo = fsops.info(carpeta / "a.txt")

    assert nodo.propietario and nodo.cifrado and nodo.tamano_claro == 9


@requiere_admin
def test_info_de_un_elemento_inexistente(area):
    from custodia.core import fsops
    from custodia.core.errors import NotFound
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    with impersonate(token), pytest.raises(NotFound):
        fsops.info(carpeta / "fantasma")


# ---------------------------------------------------------------------------
# Escribir y leer
# ---------------------------------------------------------------------------

@requiere_admin
def test_no_sobrescribe_sin_permiso_explicito(area):
    from custodia.core import fsops
    from custodia.core.errors import AlreadyExists
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    with impersonate(token):
        fsops.escribir(carpeta / "a.txt", b"original")
        with pytest.raises(AlreadyExists):
            fsops.escribir(carpeta / "a.txt", b"pisado")
        assert fsops.leer(carpeta / "a.txt") == b"original"

        fsops.escribir(carpeta / "a.txt", b"nuevo", sobrescribir=True)
        assert fsops.leer(carpeta / "a.txt") == b"nuevo"

    assert _sin_temporales(carpeta)


@requiere_admin
def test_sobrescribir_conserva_los_permisos_propios_del_archivo(area, usuario_prueba):
    """os.replace sustituye el archivo entero: sin rescate, se perdería la DACL."""
    from custodia.core import acl, fsops
    from custodia.core.acl import Perm
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    archivo = carpeta / "a.txt"
    with impersonate(token):
        fsops.escribir(archivo, b"original")
    acl.conceder(archivo, "Everyone", Perm.LEER, hereda_a_hijos=False)
    antes = [(e.principal, e.mascara, e.permitir)
             for e in acl.leer_permisos(archivo) if not e.heredado]
    assert antes

    with impersonate(token):
        fsops.escribir(archivo, b"nuevo", sobrescribir=True)

    despues = [(e.principal, e.mascara, e.permitir)
               for e in acl.leer_permisos(archivo) if not e.heredado]
    assert sorted(despues) == sorted(antes)


@requiere_admin
def test_limite_de_tamano_al_escribir_y_leer(area, monkeypatch):
    from custodia.core import config, fsops
    from custodia.core.errors import FileTooLarge
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    with impersonate(token):
        fsops.escribir(carpeta / "grande.bin", b"x" * 2048)

        monkeypatch.setattr(config, "MAX_FILE_BYTES", 1024)
        with pytest.raises(FileTooLarge):
            fsops.escribir(carpeta / "otro.bin", b"x" * 2048)
        with pytest.raises(FileTooLarge):
            fsops.leer(carpeta / "grande.bin")

    assert not (carpeta / "otro.bin").exists()


@requiere_admin
def test_contenido_ya_cifrado_no_se_vuelve_a_cifrar(area):
    """El camino del cifrado por usuario: el blob llega hecho y sale en bruto."""
    from custodia.core import fsops
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    with impersonate(token):
        fsops.escribir(carpeta / "blob.bin", b"bytes opacos", cifrar=False)
        assert fsops.leer(carpeta / "blob.bin", descifrar=False) == b"bytes opacos"
    assert (carpeta / "blob.bin").read_bytes() == b"bytes opacos"


@requiere_admin
def test_leer_lo_que_no_es_un_archivo(area):
    from custodia.core import fsops
    from custodia.core.errors import NotFound
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    with impersonate(token):
        fsops.crear_carpeta(carpeta / "sub")
        with pytest.raises(NotFound, match="es una carpeta"):
            fsops.leer(carpeta / "sub")
        with pytest.raises(NotFound, match="No existe"):
            fsops.leer(carpeta / "fantasma")


@requiere_admin
def test_carpeta_duplicada(area):
    from custodia.core import fsops
    from custodia.core.errors import AlreadyExists
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    with impersonate(token):
        fsops.crear_carpeta(carpeta / "sub")
        with pytest.raises(AlreadyExists):
            fsops.crear_carpeta(carpeta / "sub")


# ---------------------------------------------------------------------------
# Eliminar
# ---------------------------------------------------------------------------

@requiere_admin
def test_eliminar_archivo_y_carpeta_vacia(area):
    from custodia.core import fsops
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    with impersonate(token):
        fsops.escribir(carpeta / "a.txt", b"x")
        fsops.crear_carpeta(carpeta / "vacia")

        fsops.eliminar(carpeta / "a.txt")
        fsops.eliminar(carpeta / "vacia")

    assert list(carpeta.iterdir()) == []


@requiere_admin
def test_eliminar_recursivo(area):
    from custodia.core import fsops
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    with impersonate(token):
        fsops.crear_carpeta(carpeta / "arbol")
        fsops.crear_carpeta(carpeta / "arbol" / "rama")
        fsops.escribir(carpeta / "arbol" / "rama" / "hoja.txt", b"x")

        fsops.eliminar(carpeta / "arbol", recursivo=True)

    assert not (carpeta / "arbol").exists()


@requiere_admin
def test_una_carpeta_con_contenido_no_se_borra_sin_recursivo(area):
    from custodia.core import fsops
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    with impersonate(token):
        fsops.crear_carpeta(carpeta / "llena")
        fsops.escribir(carpeta / "llena" / "a.txt", b"x")

        with pytest.raises(OSError):
            fsops.eliminar(carpeta / "llena")

        assert fsops.leer(carpeta / "llena" / "a.txt") == b"x"


@requiere_admin
def test_no_se_elimina_la_raiz_ni_lo_inexistente(area, raiz):
    from custodia.core import fsops
    from custodia.core.errors import NotFound
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    with impersonate(token):
        with pytest.raises(NotFound, match="raíz"):
            fsops.eliminar(raiz, recursivo=True)
        with pytest.raises(NotFound, match="No existe"):
            fsops.eliminar(carpeta / "fantasma")

    assert raiz.exists() and carpeta.exists()


@requiere_admin
def test_el_kernel_impide_eliminar(area, usuario_prueba):
    """
    La carpeta es de solo lectura para la cuenta. No basta con vetar el archivo:
    en NTFS, el control total sobre la carpeta ya permite borrar lo que contiene.
    """
    from custodia.core import acl, fsops
    from custodia.core.acl import Perm
    from custodia.core.errors import PermissionDenied
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    cuenta, _ = usuario_prueba
    protegida = carpeta / "solo_lectura"
    protegida.mkdir()
    archivo = protegida / "a.txt"
    archivo.write_bytes(b"x")
    acl.establecer_permisos(
        protegida,
        [("Administrators", int(Perm.TOTAL), True, True),
         (cuenta.username, int(Perm.LEER), True, True)],
        romper_herencia=True,
    )

    with impersonate(token), pytest.raises(PermissionDenied):
        fsops.eliminar(archivo)

    assert archivo.exists()


# ---------------------------------------------------------------------------
# Renombrar, mover y copiar
# ---------------------------------------------------------------------------

@requiere_admin
def test_renombrar(area):
    from custodia.core import fsops
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    with impersonate(token):
        fsops.escribir(carpeta / "viejo.txt", b"datos")
        nodo = fsops.renombrar(carpeta / "viejo.txt", "nuevo.txt")
        assert fsops.leer(carpeta / "nuevo.txt") == b"datos"

    assert nodo.nombre == "nuevo.txt"
    assert not (carpeta / "viejo.txt").exists()


@requiere_admin
def test_renombrar_rechaza_colision_y_nombres_invalidos(area):
    from custodia.core import fsops
    from custodia.core.errors import AlreadyExists, InvalidPathName, NotFound
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    with impersonate(token):
        fsops.escribir(carpeta / "a.txt", b"a")
        fsops.escribir(carpeta / "b.txt", b"b")

        with pytest.raises(AlreadyExists):
            fsops.renombrar(carpeta / "a.txt", "b.txt")
        with pytest.raises(InvalidPathName):
            fsops.renombrar(carpeta / "a.txt", "CON")
        with pytest.raises(NotFound):
            fsops.renombrar(carpeta / "fantasma", "c.txt")

        assert fsops.leer(carpeta / "b.txt") == b"b"


@requiere_admin
def test_mover_a_otra_carpeta(area):
    from custodia.core import fsops
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    with impersonate(token):
        fsops.escribir(carpeta / "a.txt", b"datos")
        fsops.crear_carpeta(carpeta / "destino")

        nodo = fsops.mover(carpeta / "a.txt", carpeta / "destino")

        assert fsops.leer(carpeta / "destino" / "a.txt") == b"datos"
    assert nodo.nombre == "a.txt"
    assert not (carpeta / "a.txt").exists()


@requiere_admin
def test_mover_rechaza_destinos_invalidos(area):
    from custodia.core import fsops
    from custodia.core.errors import AlreadyExists, NotFound
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    with impersonate(token):
        fsops.escribir(carpeta / "a.txt", b"origen")
        fsops.crear_carpeta(carpeta / "destino")
        fsops.escribir(carpeta / "destino" / "a.txt", b"ya estaba")

        with pytest.raises(AlreadyExists):
            fsops.mover(carpeta / "a.txt", carpeta / "destino")
        with pytest.raises(NotFound, match="no es una carpeta"):
            fsops.mover(carpeta / "a.txt", carpeta / "a.txt")
        with pytest.raises(NotFound, match="No existe"):
            fsops.mover(carpeta / "fantasma", carpeta / "destino")

        assert fsops.leer(carpeta / "destino" / "a.txt") == b"ya estaba"


@requiere_admin
def test_copiar_archivo_y_arbol(area):
    from custodia.core import fsops
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    with impersonate(token):
        fsops.crear_carpeta(carpeta / "origen")
        fsops.escribir(carpeta / "origen" / "a.txt", b"datos")
        fsops.crear_carpeta(carpeta / "destino")

        fsops.copiar(carpeta / "origen" / "a.txt", carpeta / "destino")
        fsops.copiar(carpeta / "origen", carpeta / "destino")

        assert fsops.leer(carpeta / "destino" / "a.txt") == b"datos"
        assert fsops.leer(carpeta / "destino" / "origen" / "a.txt") == b"datos"
        assert fsops.leer(carpeta / "origen" / "a.txt") == b"datos"


@requiere_admin
def test_la_copia_hereda_los_permisos_del_destino(area):
    """El permiso restringido del original no viaja con la copia."""
    from custodia.core import acl, fsops
    from custodia.core.acl import Perm
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    with impersonate(token):
        fsops.escribir(carpeta / "a.txt", b"datos")
        fsops.crear_carpeta(carpeta / "destino")
    acl.conceder(carpeta / "a.txt", "Everyone", Perm.LEER, hereda_a_hijos=False)
    assert any(not e.heredado for e in acl.leer_permisos(carpeta / "a.txt"))

    with impersonate(token):
        fsops.copiar(carpeta / "a.txt", carpeta / "destino")

    assert not any(not e.heredado for e in acl.leer_permisos(carpeta / "destino" / "a.txt"))


@requiere_admin
def test_copiar_rechaza_colision_e_inexistentes(area):
    from custodia.core import fsops
    from custodia.core.errors import AlreadyExists, NotFound
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    with impersonate(token):
        fsops.escribir(carpeta / "a.txt", b"origen")
        fsops.crear_carpeta(carpeta / "destino")
        fsops.escribir(carpeta / "destino" / "a.txt", b"ya estaba")

        with pytest.raises(AlreadyExists):
            fsops.copiar(carpeta / "a.txt", carpeta / "destino")
        with pytest.raises(NotFound):
            fsops.copiar(carpeta / "fantasma", carpeta / "destino")

        assert fsops.leer(carpeta / "destino" / "a.txt") == b"ya estaba"


# ---------------------------------------------------------------------------
# Buscar
# ---------------------------------------------------------------------------

@requiere_admin
def test_buscar_sin_distinguir_mayusculas(area):
    from custodia.core import fsops
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    with impersonate(token):
        fsops.crear_carpeta(carpeta / "Informes")
        fsops.escribir(carpeta / "Informes" / "INFORME_final.txt", b"x")
        fsops.escribir(carpeta / "otro.txt", b"x")

        nombres = {n.nombre for n in fsops.buscar(carpeta, "  inForme ")}

    assert nombres == {"Informes", "INFORME_final.txt"}


@requiere_admin
def test_buscar_respeta_el_limite_y_el_patron_vacio(area):
    from custodia.core import fsops
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    with impersonate(token):
        for i in range(5):
            fsops.escribir(carpeta / f"dato{i}.txt", b"x")

        assert len(fsops.buscar(carpeta, "dato", limite=3)) == 3
        assert fsops.buscar(carpeta, "   ") == []


@requiere_admin
def test_buscar_no_revela_lo_que_hay_en_carpetas_vetadas(area):
    from custodia.core import fsops
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    vetada = carpeta / "vetada"
    vetada.mkdir()
    (vetada / "secreto_dentro.txt").write_bytes(b"x")
    _vetar(vetada)

    with impersonate(token):
        fsops.escribir(carpeta / "secreto_visible.txt", b"x")
        nombres = {n.nombre for n in fsops.buscar(carpeta, "secreto")}

    assert nombres == {"secreto_visible.txt"}


# ---------------------------------------------------------------------------
# Guardia y bitácora
# ---------------------------------------------------------------------------

@requiere_admin
@pytest.mark.parametrize("operacion", [
    lambda f, r: f.crear_carpeta(r / "x"),
    lambda f, r: f.escribir(r / "x.txt", b"x"),
    lambda f, r: f.leer(r / "x.txt"),
    lambda f, r: f.eliminar(r / "x.txt"),
    lambda f, r: f.renombrar(r / "x.txt", "y.txt"),
    lambda f, r: f.mover(r / "x.txt", r),
    lambda f, r: f.copiar(r / "x.txt", r),
    lambda f, r: f.info(r),
    lambda f, r: f.buscar(r, "x"),
], ids=["crear_carpeta", "escribir", "leer", "eliminar", "renombrar", "mover",
        "copiar", "info", "buscar"])
def test_ninguna_operacion_corre_sin_suplantar(raiz, operacion):
    from custodia.core import fsops

    with pytest.raises(RuntimeError, match="sin suplantación"):
        operacion(fsops, raiz)


@requiere_admin
def test_cada_operacion_queda_en_la_bitacora(area, usuario_prueba):
    from custodia.core import audit, fsops
    from custodia.core.errors import NotFound
    from custodia.core.impersonate import impersonate

    carpeta, token = area
    cuenta, _ = usuario_prueba
    with impersonate(token):
        fsops.escribir(carpeta / "a.txt", b"x")
        fsops.renombrar(carpeta / "a.txt", "b.txt")
        with pytest.raises(NotFound):
            fsops.eliminar(carpeta / "fantasma")

    audit.flush()
    assert audit.consultar(accion="renombrar")[0]["usuario"].lower() == cuenta.username.lower()
    fallo = audit.consultar(accion="eliminar")[0]
    assert fallo["exito"] is False and "NotFound" in fallo["detalle"]
