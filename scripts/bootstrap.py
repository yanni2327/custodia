# -*- coding: utf-8 -*-
"""
Inicialización del entorno. Ejecutar una vez, como administrador.

  - Crea los grupos locales de la aplicación.
  - Crea la carpeta raíz con una DACL protegida.
  - Crea la base de datos de auditoría.
  - Crea opcionalmente un usuario administrador de la aplicación.

Uso:

    python scripts/bootstrap.py
    python scripts/bootstrap.py --admin miusuario
"""
from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from custodia.core import accounts, audit, config, crypto, espacios  # noqa: E402
from custodia.core.errors import CustodiaError              # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="Inicializa el entorno de Custodia")
    parser.add_argument("--admin", help="Crea un administrador de la aplicación")
    args = parser.parse_args()

    print("=" * 60)
    print(" Inicialización de Custodia")
    print("=" * 60)

    try:
        print("\n[1] Grupos locales...")
        accounts.asegurar_grupos()
        print(f"  [OK] '{config.APP_GROUP}' y '{config.ADMIN_GROUP}'")

        print("\n[2] Carpeta raíz y estructura...")
        cuentas = [c.username for c in accounts.listar_usuarios()]
        espacios.preparar_todo(cuentas)
        print(f"  [OK] Raíz preparada en {config.STORAGE_ROOT}")
        print("       Herencia rota. Los usuarios pueden entrar en la raíz y")
        print("       crear lo suyo, pero ese permiso no baja a lo que contiene.")
        print(f"  [OK] Carpeta común '{espacios.COMPARTIDA}' para el grupo")
        if cuentas:
            print(f"  [OK] Espacio personal de: {', '.join(cuentas)}")

        print("\n[3] Bitácora de auditoría...")
        audit.init()
        audit.registrar("bootstrap", "inicializacion", str(config.STORAGE_ROOT))
        audit.close()   # vuelca la cola y cierra el archivo
        print(f"  [OK] {config.AUDIT_DB}")

        print("\n[4] Clave maestra de cifrado...")
        if config.KEY_FILE.exists():
            print(f"  [OK] Ya existe en {config.KEY_FILE}, se conserva")
            print("       (regenerarla dejaría ilegibles los archivos ya cifrados)")
        else:
            crypto.crear_clave_maestra()
            crypto.precargar_clave()   # comprobar que se puede releer
            print(f"  [OK] Creada y protegida con DPAPI en {config.KEY_FILE}")
            print("       En disco solo queda un blob que únicamente este equipo")
            print("       puede descifrar. La clave en claro jamás se escribe.")

        if args.admin:
            print(f"\n[5] Administrador '{args.admin}'...")
            password = getpass.getpass("  Contraseña: ")
            confirmacion = getpass.getpass("  Confirmar: ")
            if password != confirmacion:
                print("  [FALLO] Las contraseñas no coinciden")
                return 1
            cuenta = accounts.crear_usuario(args.admin, password, es_admin=True)
            espacios.asegurar_espacio(cuenta.username)
            print(f"  [OK] Creado. SID: {cuenta.sid}")

        print("\n" + "=" * 60)
        print(" Listo. Siguiente paso: python scripts/spike_impersonation.py")
        print("=" * 60)
        return 0

    except CustodiaError as exc:
        print(f"\n[FALLO] {exc}")
        if "administrador" in str(exc).lower() or "denegado" in str(exc).lower():
            print("Sugerencia: cierra esta ventana y abre CMD como administrador.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
