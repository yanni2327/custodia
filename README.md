# Custodia

Aplicación de escritorio para la gestión de archivos con control de acceso real
sobre Windows. La autorización de cada operación no la decide esta aplicación:
la decide el kernel, mediante cuentas locales, permisos NTFS y suplantación de
identidad. El contenido se protege además con AES-256 en reposo, y las
operaciones sensibles exigen un segundo factor (TOTP).

**Estado:** núcleo e interfaz implementados (Hito 3, ver `docs/`). Pendientes al
final de este documento.

## Requisitos

- Windows 10/11
- Python 3.12 o superior (incluido 3.14)
- Consola como **administrador**: se crean cuentas de Windows, se escriben
  ACL de NTFS y se usa DPAPI

## Puesta en marcha

```bat
py -m venv .venv
.venv\Scripts\activate.bat
pip install -r requirements.txt

python scripts\bootstrap.py
python scripts\spike_impersonation.py
pytest
```

Cobertura del núcleo (RNF-06, mínimo 80 %; hoy 73 %):

```bat
pytest --cov=custodia.core --cov-report=term-missing
```

## Abrir la interfaz

```bat
python scripts\custodia_gui.py
```

Desde una consola como administrador. En un equipo nuevo, la propia aplicación
prepara el almacén, los grupos, la clave y la bitácora, y pide la primera
cuenta administradora (no hace falta `bootstrap.py`).

## Estructura

```
src/custodia/core/
  config.py        Rutas, grupos, límites, tiempos de bloqueo, interruptores
  errors.py        Excepciones del dominio
  impersonate.py   Suplantación de identidad. El corazón del proyecto
  auth.py          LogonUser + sesiones. No se guardan contraseñas
  jail.py          Confinamiento de rutas (RF-04)
  accounts.py      Cuentas y grupos locales reales (RF-01, RF-02), incorporar
                   cuentas existentes, contraseñas temporales y cambio obligatorio
  acl.py           DACL de NTFS: leer y escribir permisos (RF-06)
  crypto.py        AES-256-GCM con clave maestra DPAPI (RF-08)
  boveda.py        Cifrado por usuario (RSA-2048 + AES-GCM). Desactivado por defecto
  fsops.py         Operaciones sobre archivos reales (RF-03)
  permissions.py   Contrato can(sujeto, ruta, acción) (RNF-03, RF-07)
  backends/
    windows.py     Producción: sondea abriendo un manejador
    memoria.py     Doble de prueba, sin sistema operativo
  audit.py         Bitácora en SQLite (RF-05)
  espacios.py      Estructura del almacén y permisos iniciales
  seguridad.py     Bloqueo por intentos fallidos
  totp.py          TOTP (RFC 6238), con detección de códigos ya usados
  segundofactor.py Secretos TOTP por usuario, protegidos con DPAPI
  descargas.py     Límite de descargas y motivo obligatorio

src/custodia/gui/
  app.py           Arranque: privilegios, primer arranque, núcleo, ingreso, ventana
  ingreso_qml.py   Ingreso (QML): contraseña, segundo factor, contraseña nueva
  login.py         Ingreso clásico de widgets: solo si Qt Quick no puede arrancar
  sesion.py        Frontera con el núcleo: encapsula la suplantación
  ventana.py       Ventana principal: aloja la vista QML y decide las acciones
  hojas.py         Controladores de cuentas, bitácora, permisos, 2FA y contraseña
  bloqueo.py       Vigilante de inactividad
  avisos.py        Avisos y preguntas (dentro de la ventana, en QML)
  qmlbase.py       Tema, fuente de iconos y proveedor de iconos para QML
  iconos.py        Logo e iconos dibujados por código
  estilo.py        Paletas clara y oscura
  qml/             Vistas: Login, Principal, Hoja*, Modal, Bloqueo, componentes
  recursos/        Tipografía Inter e icono del ejecutable (custodia.ico)

scripts/
  bootstrap.py             Inicializa grupos, raíz, bitácora y clave (desarrollo)
  spike_impersonation.py   Prueba de viabilidad de punta a punta
  custodia_gui.py          Arranca la interfaz
  generar_icono.py         Regenera recursos/custodia.ico a partir del logo

docs/
  custodia_hito3.tex       Informe del Hito 3 (IEEE); figuras en docs/figuras

tests/                     137 pruebas sobre Windows real (crean y borran
                           cuentas temporales); ver «Verificación»
```

## Las cuatro ideas del proyecto

**1. La aplicación no decide los permisos.** No hay ningún `if` que evalúe si
un usuario puede leer un archivo. Se adopta su identidad y se intenta la
operación; si Windows dice que no, se traduce ese "no" a un error.

**2. No se guardan contraseñas.** `LogonUser` las valida contra la SAM de
Windows. No hay tabla de usuarios ni hashes que administrar.

**3. Los archivos son archivos.** Viven en `C:\ProgramData\Custodia\storage` y
su pestaña Seguridad en el Explorador muestra exactamente las ACL que
administra la aplicación.

**4. El cifrado es una segunda capa, no la misma.** NTFS protege contra el
acceso por los canales normales del sistema operativo. El cifrado cubre el caso
en que esos permisos dejan de aplicarse: disco extraído, otro sistema operativo
arrancado. Son defensas contra amenazas distintas.

## Autenticación

El ingreso encadena cuatro comprobaciones, en este orden:

1. **Bloqueo por intentos.** Si la cuenta está bloqueada, ni se consulta a
   Windows. 5 fallos en 10 minutos bloquean 15 minutos (`MAX_INTENTOS`,
   `VENTANA_INTENTOS_MIN`, `BLOQUEO_MIN`). Es un bloqueo propio porque la
   política de Windows suele estar desactivada fuera de un dominio.
2. **Contraseña,** validada por Windows. Si Windows exige cambiarla (contraseña
   temporal, error 1907), la interfaz pide una nueva antes de entrar.
3. **Pertenencia.** Solo entran las cuentas de `Custodia_Usuarios`: Windows
   valida la contraseña de cualquier cuenta del equipo, y que sea correcta no
   hace a nadie usuario de la aplicación. No cuenta para el bloqueo.
4. **Segundo factor,** si la cuenta lo tiene activado.

### Segundo factor en las operaciones

El código TOTP no solo se pide al entrar: es la confirmación de toda operación
que compromete los archivos o las cuentas (`VentanaPrincipal._confirmar_con_codigo`,
la única puerta):

- Archivos: eliminar, guardar una copia, añadir, renombrar.
- Permisos: conceder y quitar.
- Cuentas: crear, eliminar, incorporar, retirar, asignar y quitar grupos,
  eliminar grupos, restablecer contraseña o segundo factor de otra cuenta.
- La propia cuenta: desactivar el segundo factor (si no, quien encontrara la
  sesión abierta podría quitarlo para saltarse lo demás).

Reglas: sin segundo factor activado esas operaciones no se permiten (se ofrece
activarlo con un QR); **cada código vale una sola vez** por sesión, también el
del ingreso (`Sesion.ultimo_contador`); cada código incorrecto cuenta para el
bloqueo y queda en la bitácora con la operación que se intentaba.

### Bloqueo por inactividad

Tras `BLOQUEO_INACTIVIDAD_MIN` (5) minutos sin ratón ni teclado, o con Ctrl+L,
una capa opaca tapa la ventana y pide la contraseña, con las mismas reglas que
el ingreso. Si sigue bloqueada `SESSION_IDLE_MINUTES` (30) minutos más, la
sesión se cierra y se libera el token.

### Contraseñas

- Un administrador puede **restablecer** la de otra cuenta: se genera una
  temporal (≈70 bits, sin caracteres que se confundan) que se muestra una sola
  vez y no se guarda ni se registra, y Windows marca la cuenta para exigir el
  cambio. Como las cuentas que crea Custodia tienen «la contraseña nunca
  expira» (con lo que Windows ignoraría esa marca), se quita al restablecer y
  se repone tras el cambio.
- Cada persona puede **cambiar la suya** desde el perfil, con la actual.
- Regla propia: al menos 8 caracteres, con letras y números. Windows aplica
  además su política, si la hay.

## Dos caminos hacia el mismo veredicto

La aplicación puede llegar de dos maneras a saber si un usuario tiene permiso:

- `fsops` **intenta** la operación bajo suplantación y traduce el error que
  devuelve el kernel.
- `permissions.can()` **sondea** por adelantado abriendo un manejador.

Ambos terminan en el mismo motor de autorización de Windows, así que no pueden
contradecirse; `test_la_respuesta_coincide_con_la_operacion_real` lo verifica.
El primero es el que autoriza de verdad; el segundo existe para que la interfaz
pueda mostrar los permisos efectivos sin intentar la operación. `can()` nunca
sustituye al intento real, porque entre la consulta y la operación los permisos
podrían cambiar.

## Decisiones de arquitectura

**Sin servidor local ni navegador (RNF-07).** La interfaz llama directamente al
núcleo, sin HTTP en medio. La aplicación entera corre con los privilegios con
que se lanza; el ejecutable lleva un manifiesto `requireAdministrator`.

**Interfaz en QML, lógica en Python.** Las vistas (`gui/qml/`) solo dibujan y
avisan de lo que la persona hace a un objeto puente; Python decide. La ventana
principal es un `QMainWindow` con un `QQuickWidget`. Las acciones que pueden
abrir un aviso se difieren un ciclo del bucle de eventos para no ejecutarse
dentro de un manejador de QML.

**`Sesion` es la frontera.** Ningún archivo de la interfaz sabe que la
suplantación existe; concentrarla en una clase evita que un `return` temprano
en un manejador deje el hilo de la interfaz con la identidad de otro usuario.

**Comprobaciones lentas en otro hilo.** `LogonUser` tarda a propósito cuando
falla. Ingreso y desbloqueo se comprueban en un hilo que no suplanta a nadie.

**Suplantación por hilo.** En Windows la suplantación afecta al hilo, no al
proceso. `RevertToSelf()` va siempre en un `finally`, y `impersonate()` nunca
debe usarse dentro de una función `async`.

**Escritura atómica.** El contenido va a un temporal en la misma carpeta y solo
al final se renombra con `os.replace`. Una operación denegada no deja archivos
parciales ni temporales huérfanos (RNF-05).

**La clave maestra se carga antes de suplantar.** El archivo de clave solo lo
pueden leer Administradores y SYSTEM, y las operaciones ocurren bajo
identidades suplantadas sin ese privilegio. Por eso `crypto.precargar_clave()`
se llama al arrancar, y dentro de la suplantación solo se consulta el caché.

**La bitácora se escribe fuera de la suplantación.** `registrar()` solo encola
el evento; un hilo escritor que nunca suplanta vuelca la cola. Si el usuario
pudiera escribir la bitácora, podría manipular el registro de sus acciones.

**Secretos con la misma protección que la clave.** Los secretos TOTP (DPAPI) y
el registro de intentos fallidos van en archivos restringidos a Administradores
y SYSTEM: nadie lee el secreto de otro ni borra su propio contador.

**Alcance de DPAPI.** La clave maestra se protege con ámbito de máquina, porque
las operaciones ocurren bajo identidades suplantadas distintas. Consecuencia
honesta: cualquier proceso de esta máquina podría llamar a `CryptUnprotectData`
sobre el blob. Se mitiga con una ACL restrictiva y entropía propia, pero no se
elimina.

## Salvaguardas de administración

Crear, modificar y borrar cuentas reales del sistema exige cuidado:

- `_assert_gestionable` rechaza cualquier cuenta que no esté en
  `Custodia_Usuarios`, y las integradas de Windows se reconocen por su RID
  (500, 501, 503, 504), no solo por el nombre.
- Las cuentas que **ya existían** en Windows (incorporadas) no se borran desde
  la aplicación: solo se **retiran** de ella. Las creadas por Custodia llevan
  la marca `Custodia:` en el comentario.
- Nadie se retira a sí mismo ni se saca de los administradores; nunca se
  retira al último administrador; los dos grupos internos no se eliminan.

## Una asimetría que conviene declarar

El acceso a los archivos lo autoriza el kernel, incluido el cambio de permisos:
`escribir_permisos` suplanta al usuario, así que hace falta el derecho
WRITE_DAC, que tienen los administradores y el propietario del objeto.

La administración de cuentas es la excepción. Crear una cuenta de Windows exige
que el proceso esté elevado, sea quien sea el que inició sesión en Custodia, así
que la comprobación es de la aplicación (`es_admin`). Es el único punto donde la
autorización no la da Windows.

## Construir el ejecutable (RNF-07)

```bat
.venv\Scripts\python.exe -m PyInstaller custodia.spec --noconfirm
```

Mejor desde una consola **sin** elevar: PyInstaller lo desaconseja y la versión
7 lo impedirá; solo la aplicación necesita elevación (va en su manifiesto).

Queda en `dist\Custodia.exe` (≈170 MB). Un ejecutable único se descomprime en
una carpeta temporal en cada arranque, así que tarda unos segundos en abrir.

El icono es `src/custodia/gui/recursos/custodia.ico`. Si cambia el logo:

```bat
.venv\Scripts\python.exe scripts\generar_icono.py
```

## Verificación

137 pruebas sobre Windows real (136 pasan, 1 se omite). Mediciones actuales:

| Requisito | Resultado |
|-----------|-----------|
| RNF-01 sin suplantaciones remanentes | Cumple |
| RNF-02 ≤ 500 ms por 10 MB | 49,5 ms |
| RNF-03 contrato contra ambos backends | Cumple |
| RNF-05 sin archivos parciales | Cumple |
| RNF-06 cobertura ≥ 80 % | **73 %** (no cumple) |
| RNF-08 sobrecarga del cifrado ≤ 200 ms | 14,8 ms |

## Pendiente

- Respaldo y recuperación de la clave maestra (control C13 del análisis de
  riesgos): es el único control del diseño sin implementar.
- Subir la cobertura del núcleo al 80 % (RNF-06).
- Prueba de usabilidad con dos personas ajenas al desarrollo (RNF-04).
- Prueba del ejecutable en un equipo limpio (RNF-07) y reducir su tamaño
  excluyendo los módulos de Qt Quick que no se usan.
