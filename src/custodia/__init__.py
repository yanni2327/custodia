# -*- coding: utf-8 -*-
"""
Custodia — gestión de archivos con control de acceso real sobre Windows.

La autorización de cada operación no la decide esta aplicación: la decide el
kernel de Windows, mediante cuentas locales, permisos NTFS y suplantación de
identidad. El contenido se protege además con cifrado AES-256 en reposo.
"""
import sys

if sys.platform != "win32":
    raise RuntimeError(
        "Custodia solo funciona en Windows: usa las APIs de seguridad nativas "
        "(LogonUser, ImpersonateLoggedOnUser, DACLs de NTFS, DPAPI), que no "
        "tienen equivalente en otras plataformas."
    )

__version__ = "0.2.0"
