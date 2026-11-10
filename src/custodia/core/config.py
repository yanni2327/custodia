# -*- coding: utf-8 -*-
"""
Configuración central del servicio Custodia.

Todo valor que pueda cambiar entre máquinas vive aquí y se puede sobreescribir
con variables de entorno. Nada de credenciales: en este proyecto las
contraseñas las guarda Windows, no nosotros.
"""
from __future__ import annotations

import os
from pathlib import Path

# ---------------------------------------------------------------------------
# Rutas
# ---------------------------------------------------------------------------

#: Raíz del "sistema de archivos" administrado. TODO lo que la aplicación
#: toque debe estar por debajo de esta carpeta. El módulo jail.py se encarga
#: de garantizarlo.
STORAGE_ROOT = Path(
    os.getenv("CUSTODIA_STORAGE_ROOT", r"C:\ProgramData\Custodia\storage")
)

#: Base de datos SQLite de la bitácora de auditoría.
AUDIT_DB = Path(os.getenv("CUSTODIA_AUDIT_DB", r"C:\ProgramData\Custodia\audit.db"))

#: Escribir anclas de la bitácora en el Visor de eventos de Windows (C16). Solo
#: se apaga en pruebas, para no llenar el registro de Application del equipo.
ANCLAR_BITACORA = os.getenv("CUSTODIA_ANCLAR_BITACORA", "1") not in ("0", "false", "False")

#: Impedir la entrada si la unidad del almacén no tiene BitLocker activo (C15).
EXIGIR_BITLOCKER = os.getenv("CUSTODIA_EXIGIR_BITLOCKER", "0") not in ("0", "false", "False")

#: Clave maestra de cifrado, protegida con DPAPI. Nunca contiene la clave en
#: claro: lo que se guarda es un blob que solo esta máquina puede descifrar.
KEY_FILE = Path(os.getenv("CUSTODIA_KEY_FILE", r"C:\ProgramData\Custodia\master.key"))

#: Días que se conserva la copia de la clave anterior tras restaurar un
#: respaldo (control C13). Es el blob DPAPI, nunca la clave en claro.
RETENCION_COPIA_CLAVE_DIAS = int(os.getenv("CUSTODIA_RETENCION_COPIA_CLAVE_DIAS", "30"))

# ---------------------------------------------------------------------------
# Cuentas de Windows
# ---------------------------------------------------------------------------

#: Grupo local que marca qué cuentas de Windows pertenecen a esta aplicación.
#: Es la salvaguarda más importante del proyecto: accounts.py se niega a
#: modificar o borrar cualquier cuenta que no sea miembro de este grupo, así
#: que un bug no puede tocar al Administrador ni a cuentas del sistema.
APP_GROUP = os.getenv("CUSTODIA_APP_GROUP", "Custodia_Usuarios")

#: Grupo local cuyos miembros son administradores DE LA APLICACIÓN.
#: No confundir con el grupo "Administradores" de Windows.
ADMIN_GROUP = os.getenv("CUSTODIA_ADMIN_GROUP", "Custodia_Administradores")

#: Prefijo opcional para los nombres de usuario creados por la aplicación.
#: Deja "" si prefieres nombres limpios; el grupo APP_GROUP ya identifica
#: las cuentas propias.
USER_PREFIX = os.getenv("CUSTODIA_USER_PREFIX", "")

#: Servidor donde se crean las cuentas. None = máquina local.
#: Este proyecto trabaja solo con cuentas locales, no con dominio.
SERVER = None

# ---------------------------------------------------------------------------
# Sesiones
# ---------------------------------------------------------------------------

#: Minutos de inactividad tras los cuales una sesión se cierra y su token
#: de Windows se libera.
SESSION_IDLE_MINUTES = int(os.getenv("CUSTODIA_SESSION_IDLE_MINUTES", "30"))

#: Minutos sin actividad (ratón o teclado) tras los cuales la interfaz se
#: bloquea y pide la contraseña. 0 desactiva el bloqueo automático. Una vez
#: bloqueada, si pasan SESSION_IDLE_MINUTES más sin desbloquear, la sesión se
#: cierra del todo y se vuelve al inicio de sesión.
BLOQUEO_INACTIVIDAD_MIN = int(os.getenv("CUSTODIA_BLOQUEO_INACTIVIDAD_MIN", "5"))

# ---------------------------------------------------------------------------
# Límites
# ---------------------------------------------------------------------------

#: Tamaño máximo de archivo que el servicio acepta escribir, en bytes.
MAX_FILE_BYTES = int(os.getenv("CUSTODIA_MAX_FILE_BYTES", str(64 * 1024 * 1024)))

# ---------------------------------------------------------------------------
# Cifrado
# ---------------------------------------------------------------------------

#: Cifrar el contenido de los archivos en reposo (RF-08).
#: Se puede desactivar para medir el sobrecosto que exige el RNF-08, que pide
#: comparar la misma operación con y sin cifrado.
CIFRADO_ACTIVO = os.getenv("CUSTODIA_CIFRADO", "1") not in ("0", "false", "False")

#: Cifrado POR USUARIO (de sobre). En vez de una clave maestra única, cada
#: archivo se cifra con una clave propia envuelta con la clave pública de cada
#: persona autorizada. Es más fuerte —un administrador sin la contraseña del
#: dueño no puede leer el contenido—, a cambio de más complejidad. Apagado por
#: defecto: se enciende con CUSTODIA_CIFRADO_POR_USUARIO=1 para probarlo sin
#: alterar el funcionamiento ya validado.
CIFRADO_POR_USUARIO = os.getenv("CUSTODIA_CIFRADO_POR_USUARIO", "0") not in (
    "0", "false", "False"
)

#: Archivos que se migran al cifrado por usuario en cada inicio de sesión. Lo
#: que no alcance se migra en los siguientes, para no demorar el ingreso.
MIGRACION_MAX_POR_INGRESO = int(os.getenv("CUSTODIA_MIGRACION_MAX_POR_INGRESO", "200"))

#: Almacén de identidades (par de claves por usuario) del cifrado por usuario.
#: Las públicas van en claro; las privadas, cifradas con la contraseña de cada
#: cuenta. Protegido por ACL de Administradores y SYSTEM, como la clave maestra.
BOVEDA_FILE = Path(
    os.getenv("CUSTODIA_BOVEDA_FILE", r"C:\ProgramData\Custodia\identidades.json")
)

# ---------------------------------------------------------------------------
# Refuerzos de autenticación
# ---------------------------------------------------------------------------

#: Secretos del segundo factor (TOTP), uno por usuario. Cada secreto se guarda
#: protegido con DPAPI y el archivo lleva una ACL que solo permite
#: Administradores y SYSTEM, igual que la clave maestra.
SEGUNDO_FACTOR_FILE = Path(
    os.getenv("CUSTODIA_2FA_FILE", r"C:\ProgramData\Custodia\2fa.dat")
)

#: Nombre que aparece en la app de autenticación (Google Authenticator, etc.).
EMISOR_2FA = os.getenv("CUSTODIA_EMISOR_2FA", "Custodia")

#: Registro de intentos de inicio de sesión fallidos, para el bloqueo por
#: fuerza bruta. También protegido por ACL de Administradores y SYSTEM.
INTENTOS_FILE = Path(
    os.getenv("CUSTODIA_INTENTOS_FILE", r"C:\ProgramData\Custodia\intentos.dat")
)

#: Intentos fallidos permitidos dentro de la ventana antes de bloquear.
MAX_INTENTOS = int(os.getenv("CUSTODIA_MAX_INTENTOS", "5"))

#: Ventana (minutos) en la que se cuentan los intentos fallidos.
VENTANA_INTENTOS_MIN = int(os.getenv("CUSTODIA_VENTANA_INTENTOS_MIN", "10"))

#: Duración (minutos) del bloqueo una vez superados los intentos.
BLOQUEO_MIN = int(os.getenv("CUSTODIA_BLOQUEO_MIN", "15"))

# ---------------------------------------------------------------------------
# Descargas (exportación de copias fuera de Custodia)
# ---------------------------------------------------------------------------

#: Clave de descarga por usuario (un segundo secreto, distinto del de inicio de
#: sesión) y conteo de descargas para frenar la exfiltración masiva. Se guarda
#: solo el hash scrypt de la clave, nunca la clave; el archivo lleva la ACL de
#: Administradores y SYSTEM.
DESCARGAS_FILE = Path(
    os.getenv("CUSTODIA_DESCARGAS_FILE", r"C:\ProgramData\Custodia\descargas.dat")
)

#: Descargas permitidas dentro de la ventana antes de bloquear nuevas.
MAX_DESCARGAS = int(os.getenv("CUSTODIA_MAX_DESCARGAS", "20"))

#: Ventana (minutos) en la que se cuentan las descargas.
VENTANA_DESCARGAS_MIN = int(os.getenv("CUSTODIA_VENTANA_DESCARGAS_MIN", "10"))

#: Duración (minutos) del bloqueo de descargas una vez superado el límite.
BLOQUEO_DESCARGAS_MIN = int(os.getenv("CUSTODIA_BLOQUEO_DESCARGAS_MIN", "15"))
