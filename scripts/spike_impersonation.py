# -*- coding: utf-8 -*-
"""
PRUEBA DE VIABILIDAD — ejecutar esto ANTES de escribir nada más.

Verifica de punta a punta que el mecanismo sobre el que se apoya todo el
proyecto funciona en esta máquina:

  1. Se pueden crear cuentas locales de Windows.
  2. Se pueden escribir DACLs de NTFS.
  3. La suplantación cambia realmente la identidad del hilo.
  4. El kernel deniega el acceso a un usuario sin permiso.

Si el paso 4 falla con PermissionError, el proyecto es viable: el "no" viene
del sistema operativo, no de código nuestro. Ese es todo el argumento.

Uso (consola como ADMINISTRADOR):

    python scripts/spike_impersonation.py

Limpia lo que crea al terminar.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import ntsecuritycon as con           # noqa: E402
import win32api                        # noqa: E402
import win32net                        # noqa: E402
import win32netcon                     # noqa: E402
import win32security                   # noqa: E402
import pywintypes                      # noqa: E402

USUARIO = "custodia_prueba"
PASSWORD = "Prueba.2026!SOP"


def _activar_colores() -> tuple[str, str, str]:
    """
    Habilita las secuencias ANSI en la consola de Windows.

    CMD no las interpreta por defecto: hay que activar el bit
    ENABLE_VIRTUAL_TERMINAL_PROCESSING en el modo de la consola, o los códigos
    se imprimen literalmente como "←[92m". Si no se puede activar (consolas
    antiguas, salida redirigida a un archivo), se devuelven cadenas vacías y el
    texto sale sin color pero legible.
    """
    import ctypes

    ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
    STD_OUTPUT_HANDLE = -11

    try:
        k32 = ctypes.windll.kernel32
        handle = k32.GetStdHandle(STD_OUTPUT_HANDLE)
        modo = ctypes.c_uint32()
        if not k32.GetConsoleMode(handle, ctypes.byref(modo)):
            return "", "", ""
        if not k32.SetConsoleMode(handle, modo.value | ENABLE_VIRTUAL_TERMINAL_PROCESSING):
            return "", "", ""
        return "\033[92m", "\033[91m", "\033[0m"
    except Exception:
        return "", "", ""


VERDE, ROJO, RESET = _activar_colores()


def ok(msg):
    print(f"  {VERDE}[OK]{RESET} {msg}")


def fallo(msg):
    print(f"  {ROJO}[FALLO]{RESET} {msg}")


def limpiar(carpeta: Path | None):
    try:
        win32net.NetUserDel(None, USUARIO)
    except Exception:
        pass
    if carpeta and carpeta.exists():
        import shutil
        shutil.rmtree(carpeta, ignore_errors=True)


def main() -> int:
    print("=" * 68)
    print(" PRUEBA DE VIABILIDAD — suplantación de identidad en Windows")
    print("=" * 68)

    carpeta = None
    token = None

    try:
        # --- 1. Crear una cuenta local real ---------------------------------
        print("\n[1] Creando cuenta local de Windows...")
        try:
            win32net.NetUserAdd(None, 1, {
                "name": USUARIO,
                "password": PASSWORD,
                "priv": win32netcon.USER_PRIV_USER,
                "home_dir": None,
                "comment": "Cuenta temporal de prueba de Custodia",
                "flags": win32netcon.UF_SCRIPT | win32netcon.UF_DONT_EXPIRE_PASSWD,
                "script_path": None,
            })
            ok(f"Cuenta '{USUARIO}' creada")
        except pywintypes.error as exc:
            if exc.winerror == 2224:
                ok(f"La cuenta '{USUARIO}' ya existía, se reutiliza")
            elif exc.winerror == 5:
                fallo("Acceso denegado. Abre la consola COMO ADMINISTRADOR.")
                return 1
            elif exc.winerror == 2245:
                fallo("La contraseña no cumple la política de la máquina. "
                      "Cambia la constante PASSWORD por una más compleja.")
                return 1
            else:
                fallo(f"Error {exc.winerror}: {exc.strerror}")
                return 1

        # --- 2. Carpeta con permisos restringidos ---------------------------
        print("\n[2] Creando carpeta con DACL restrictiva...")
        carpeta = Path(tempfile.mkdtemp(prefix="custodia_spike_"))
        secreto = carpeta / "confidencial.txt"
        secreto.write_text("Si el usuario de prueba lee esto, algo falla.", encoding="utf-8")

        # DACL protegida: se rompe la herencia y solo queda quien pongamos.
        # Los grupos integrados se resuelven por SID conocido, no por nombre:
        # "Administrators" no existe en un Windows en español.
        admins_sid = win32security.ConvertStringSidToSid("S-1-5-32-544")
        yo_sid, _, _ = win32security.LookupAccountName(None, win32api.GetUserName())

        dacl = win32security.ACL()
        dacl.AddAccessAllowedAceEx(
            win32security.ACL_REVISION_DS,
            con.OBJECT_INHERIT_ACE | con.CONTAINER_INHERIT_ACE,
            con.FILE_ALL_ACCESS, admins_sid,
        )
        dacl.AddAccessAllowedAceEx(
            win32security.ACL_REVISION_DS,
            con.OBJECT_INHERIT_ACE | con.CONTAINER_INHERIT_ACE,
            con.FILE_ALL_ACCESS, yo_sid,
        )
        # Obsérvese que el usuario de prueba NO aparece en la lista.

        win32security.SetNamedSecurityInfo(
            str(carpeta), win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION
            | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
            None, None, dacl, None,
        )
        win32security.SetNamedSecurityInfo(
            str(secreto), win32security.SE_FILE_OBJECT,
            win32security.DACL_SECURITY_INFORMATION
            | win32security.PROTECTED_DACL_SECURITY_INFORMATION,
            None, None, dacl, None,
        )
        ok(f"Carpeta protegida en {carpeta}")

        # --- 3. Autenticar contra Windows -----------------------------------
        print("\n[3] Autenticando con LogonUser...")
        token = win32security.LogonUser(
            USUARIO, ".", PASSWORD,
            win32security.LOGON32_LOGON_NETWORK,
            win32security.LOGON32_PROVIDER_DEFAULT,
        )
        ok("Windows validó las credenciales y devolvió un token de acceso")
        print("      (nota: ninguna contraseña se guardó en ninguna base de datos)")

        # --- 4. Suplantar y comprobar la identidad --------------------------
        print("\n[4] Suplantando identidad...")
        antes = win32api.GetUserName()
        win32security.ImpersonateLoggedOnUser(token)
        try:
            durante = win32api.GetUserName()
            if durante.lower() != USUARIO.lower():
                fallo(f"La identidad no cambió: sigue siendo '{durante}'")
                return 1
            ok(f"Identidad del hilo: '{antes}' -> '{durante}'")

            # --- 5. La prueba de fuego ---------------------------------------
            print("\n[5] Intentando leer el archivo protegido como el usuario suplantado...")
            try:
                secreto.read_text(encoding="utf-8")
                fallo("SE PUDO LEER. La suplantación no está aplicando permisos.")
                print("      Revisa si la carpeta temporal hereda permisos de 'Usuarios'.")
                return 1
            except PermissionError:
                ok("PermissionError — el acceso fue denegado")
                print(f"      {VERDE}Ese 'no' lo dio el kernel de Windows, no código nuestro.{RESET}")
                print(f"      {VERDE}El proyecto es viable por este camino.{RESET}")
        finally:
            win32security.RevertToSelf()

        despues = win32api.GetUserName()
        if despues != antes:
            fallo(f"RevertToSelf no restauró la identidad: '{despues}'")
            return 1
        ok(f"Identidad restaurada a '{despues}'")

        print("\n" + "=" * 68)
        print(f" {VERDE}TODAS LAS COMPROBACIONES PASARON{RESET}")
        print("=" * 68)
        return 0

    finally:
        if token is not None:
            try:
                token.Close()
            except Exception:
                pass
        print("\nLimpiando cuenta y carpeta de prueba...")
        limpiar(carpeta)


if __name__ == "__main__":
    sys.exit(main())
