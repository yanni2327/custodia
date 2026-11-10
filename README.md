# Custodia

Aplicación de escritorio para la gestión de archivos con control de acceso real
sobre Windows. La autorización de cada operación no la decide esta aplicación:
la decide el kernel, mediante cuentas locales, permisos NTFS y suplantación de
identidad. El contenido se protege además con AES-256 en reposo, y las
operaciones sensibles exigen un segundo factor (TOTP).

**Estado:** núcleo e interfaz implementados (Hito 3). Pendientes al
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

Cobertura del núcleo (RNF-06, mínimo 80 %; hoy 92 %):

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
  respaldo.py      Respaldo y recuperación de la clave maestra (C13)
  boveda.py        Cifrado por usuario (RSA-2048 + AES-GCM). Desactivado por defecto
  recuperacion.py  Clave de recuperación del cifrado por usuario, en USB (C20)
  migracion.py     Paso de archivos con clave maestra al cifrado por usuario (C20)
  fsops.py         Operaciones sobre archivos reales (RF-03)
  permissions.py   Contrato can(sujeto, ruta, acción) (RNF-03, RF-07)
  backends/
    windows.py     Producción: sondea abriendo un manejador
    memoria.py     Doble de prueba, sin sistema operativo
  audit.py         Bitácora en SQLite, encadenada con SHA-256 (RF-05, C16)
  volumen.py       Comprobación de BitLocker en la unidad del almacén (C15)
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

tests/                     382 pruebas sobre Windows real (crean y borran
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
- La clave maestra: exportar y restaurar su respaldo.

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

## Respaldo y recuperación de la clave maestra (C13)

El blob de `master.key` solo se abre en este equipo. El respaldo es un archivo
`.custodiakey` con la clave cifrada con una contraseña de recuperación de al
menos 12 caracteres (scrypt y AES-256-GCM). **Quien tenga el archivo y la
contraseña puede descifrar todos los archivos**: guárdalos en lugares distintos.

**Exportar.** Perfil → Respaldo de la clave → Exportar respaldo, con el código
TOTP. Solo administradores. Conviene guardarlo en una USB; el programa no lo
acepta dentro del almacén ni junto a la clave.

**Recuperar en este equipo.** Si `master.key` se dañó o se perdió, Custodia
arranca igual y avisa, sin generar otra clave si el almacén ya tiene archivos
cifrados. Entra con una cuenta administradora y usa Perfil → Respaldo de la
clave → Restaurar respaldo, con el código TOTP.

**Recuperar en un equipo nuevo.**

1. Copia el almacén a `C:\ProgramData\Custodia\storage`, antes de abrir Custodia
   o antes de crear archivos nuevos.
2. Abre Custodia y crea la cuenta administradora que pide.
3. Activa el segundo factor y restaura el respaldo.
4. Vuelve a crear las demás cuentas y a activar su segundo factor.

El respaldo solo contiene la clave maestra. No incluye las cuentas ni el segundo
factor, porque `2fa.dat` está protegido con DPAPI y no sirve en otro equipo, ni
`identidades.json` si se usa el cifrado por usuario. Los permisos NTFS de cuentas
del equipo anterior hay que revisarlos.

Antes de escribir, la restauración comprueba que la clave abra un archivo del
almacén. Si hay archivos y ninguno abre, se rechaza y no se modifica nada. La
clave reemplazada se conserva 30 días como `master.key.anterior-<fecha>`: es el
blob DPAPI, con la misma ACL, nunca la clave en claro.

## Integridad de la bitácora (C16)

Cada registro guarda el SHA-256 de su contenido y del hash del anterior
(esquema de Schneier y Kelsey). Cada 50 eventos y al cerrar, el último id y su
hash se copian al Visor de eventos de Windows (registro Application, origen
«Custodia»). Un administrador lo comprueba con «Verificar integridad», en la
vista de bitácora, y esa comprobación también queda registrada.

Qué detecta:

- Editar cualquier campo de un registro.
- Borrar registros del medio, y huecos en la numeración.
- Insertar registros que no pertenecen a la cadena.
- Borrar los últimos registros, si queda por detrás de un ancla.
- Recalcular la cadena, si algún registro recalculado tiene un ancla: el hash ya
  no coincide con el del Visor de eventos.

Qué no detecta:

- Un administrador puede recalcular la cadena. La única diferencia que queda es
  la de las anclas, así que si también borra o falsifica los eventos del Visor,
  la manipulación no se ve. La cadena hace la alteración evidente; no la impide.
- Cambios en los eventos posteriores a la última ancla: un borrado o un recálculo
  de ese tramo, de hasta 49 registros, no deja rastro hasta el siguiente cierre.
- Lo que nunca se registró. Tampoco garantiza que la hora del equipo sea correcta.
- Si el Visor de eventos rota y descarta anclas antiguas, ya no se puede comparar
  con ellas. Los registros previos a la migración se encadenan tal como estaban:
  lo alterado antes de esa fecha no se puede saber.

## Cifrado de volumen (C15)

Al iniciar se consulta BitLocker en la unidad del almacén. Si está sin proteger,
queda en la bitácora y el administrador ve en su perfil qué hacer. Con
`CUSTODIA_EXIGIR_BITLOCKER=1`, además, la aplicación no deja entrar. Si la consulta
falla, el estado es «desconocido» y no bloquea, para que un fallo de WMI no deje a
nadie fuera. Custodia comprueba BitLocker, no lo activa; en Windows Home depende
de que el equipo admita el cifrado del dispositivo.

## Cifrado por usuario (C20)

Está desactivado por defecto. Con él, cada archivo personal se cifra para quienes
pueden leerlo, y un administrador sin su contraseña no puede abrirlo.

**Para activarlo:**

1. Un administrador crea la clave de recuperación en Perfil → Respaldo de la clave.
   El archivo `.custodiarec` lo guarda el dueño del computador en una USB, con una
   contraseña propia y una segunda copia en otro lugar.
2. Se define `CUSTODIA_CIFRADO_POR_USUARIO=1`. Sin la clave de recuperación, la
   opción no tiene efecto.
3. Cada persona, al entrar, recibe su identidad y su carpeta personal se migra.

Un archivo solo se migra si todos los que pueden leerlo seguirán pudiendo. Si lo
lee un grupo o una cuenta que aún no tiene identidad, sigue con la clave maestra.
`Compartida` no se migra, porque la abre un grupo entero: su contenido sigue al
alcance de quien tenga la clave maestra.

**Si alguien pierde su contraseña,** al entrar con la nueva recibe una identidad
nueva y no puede abrir sus archivos. Con la USB, un administrador usa «Recuperar
archivos de una cuenta» y se los devuelve. Sin la USB o su contraseña, se pierden.

El respaldo `.custodiakey` guarda junto a él una copia de las identidades, en un
archivo `.identidades`: hay que conservar los dos.

Qué no cubre:

- Quien tenga la USB y su contraseña puede leer todo.
- Un administrador con acceso al proceso puede llegar a una clave privada mientras
  la sesión de esa persona está abierta.
- Las claves públicas no van firmadas. Sustituir la de alguien se detecta cuando
  esa persona entra, pero lo compartido con ella entre tanto queda envuelto para la
  clave falsa. Un administrador que altere a la vez la clave de recuperación y una
  identidad provoca que esta se regenere, y el problema aparece al usar la USB.
- Tras migrar, los bloques del archivo v1 pueden seguir en el disco.

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

382 pruebas sobre Windows real (381 pasan, 1 se omite). Mediciones actuales:

| Requisito | Resultado |
|-----------|-----------|
| RNF-01 sin suplantaciones remanentes | Cumple |
| RNF-02 ≤ 500 ms por 10 MB | 49,5 ms |
| RNF-03 contrato contra ambos backends | Cumple |
| RNF-05 sin archivos parciales | Cumple |
| RNF-06 cobertura ≥ 80 % | 92 % (cumple) |
| RNF-08 sobrecarga del cifrado ≤ 200 ms | 14,8 ms |

## Pendiente

- Probar la restauración del respaldo de la clave (C13) en un segundo equipo
  físico: hoy está probada en este equipo, simulando la pérdida de la clave.
- Activar el cifrado por usuario por defecto (C20), cuando no queden archivos con
  clave maestra fuera de `Compartida`.
- Prueba de usabilidad con dos personas ajenas al desarrollo (RNF-04).
- Prueba del ejecutable en un equipo limpio (RNF-07) y reducir su tamaño
  excluyendo los módulos de Qt Quick que no se usan.
