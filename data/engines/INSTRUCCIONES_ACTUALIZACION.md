Instrucciones para actualizar motores
Regla principal
Cada archivo es un motor independiente. No pegues un motor dentro de otro ni edites `data/dashboard.json`: Python lo reconstruye. El Directorio define el universo oficial; si un CeCo no existe ahí, sus valores quedan en blanco y la auditoría lo reporta.
Contratos
Base_Perfil Tienda.xlsx
Hojas obligatorias: `Perfil` e `Instrucciones_Ejemplo`.
Llave única por fila: `MES_NUM + CeCo`.
`MES_NUM`: entero de `1` a `12`; también se aceptan `YYYYMM` y etiquetas como `1_ene`.
Se permiten más o menos filas, CeCos y meses. No repitas una misma combinación `MES_NUM + CeCo`.
Mantén los encabezados de métricas. `-100%` comparativo significa “No aplica” y se convierte a blanco.
DT se interpreta como `mm:ss`; valores fuera del rango operativo de 00:20 a 30:00 quedan en blanco y se auditan como atípicos.
Base_Perfil Tienda.csv y Base_Perfil Tienda_2.csv
Exportación UTF-16 con BOM o UTF-8 del reporte original; separador coma, punto y coma o tabulador.
El pipeline busca el encabezado real que contiene `Mes` y `Tiendas` aunque existan líneas de título o cambie el orden de las columnas. Los encabezados duplicados y las filas incompletas cancelan la construcción.
`Mes` usa `YYYYMM`; `Tiendas` contiene el CeCo.
Se validan y cruzan por separado. Aumentar o disminuir tiendas no requiere cambios de código.
`Base_Perfil Tienda_2.csv` debe conservar: `ADT Real`, `Venta $`, `Var Ventas vs Ppto (%)`, `AWS $`, `Ticket Prom Real`, `Ticket Prom AA` y `Var Ticket vs AA (%)`.
`Ticket Prom Ppto` y `Var Ticket vs Ppto (%)` son referencias opcionales. Cuando no se exportan, quedan en blanco y se registra una advertencia; no se inventan valores ni se detiene la publicación de los datos disponibles. Si se incluyen, se conservan sus comparativos.
Sólo se publica el año más reciente con periodos válidos y tiendas del Directorio. Las filas de otros años se reportan y no se mezclan con el año seleccionado. Las claves duplicadas del mismo motor y periodo siguen siendo un error bloqueante.
Directorio_Perfil Tienda.csv
Codificación UTF-8 y llave única `CC` de cinco dígitos.
Se requiere `Estatus`: sólo las filas cuyo valor es `Abierta` entran al tablero y a todos los cruces. Se excluyen cierres temporales, definitivos, próximas aperturas y estatus vacíos. Si falta Estatus, no se publica una selección supuesta.
El nombre de la tienda puede venir en `Tienda` o `CC Nombre`. Se admiten diferencias de acentos, espacios y mayúsculas en los encabezados. No se acepta una columna ambigua ni un CC abierto duplicado.
Las fechas de apertura admiten fechas de Excel, números de serie, `DD/MM/YYYY` y `DD/MM/YY`, incluso con espacios alrededor de `/`. Los años de dos dígitos usan la convención 00–68 = 2000–2068 y 69–99 = 1969–1999. Las fechas inválidas quedan en blanco y se auditan.
Actualiza altas/bajas aquí primero. Los filtros Tienda, DM y Región se generan dinámicamente.
`Tienda` y `Nombre APP y Signage` funcionan como alias; sólo se usa un alias si coincide con un único CeCo.
Base_Mix.csv
No se guarda monolítico porque supera 25 MB.
Ejecuta `split_mix.py`; genera una parte por mes y `mix/manifest.json` con filas, tamaño y SHA-256.
No renombres ni edites manualmente las partes. El build comprueba el checksum antes de usarlas.
Si una parte llegara a 24 MB, el script se detiene para evitar un archivo incompatible con GitHub Web.
Query.xlsx
Hoja `Query` o `query`, sin distinguir mayúsculas. Se requiere un identificador de empleado (`NUM_EMP`) y un centro de costo (`cc`, `CeCo` o `CCOSTO`).
Sólo `CCOSTO`/`Centro de Costo` admite el formato compuesto distrito de 3 dígitos + CeCo de 5; un valor numérico de 7 dígitos se completa con el cero inicial perdido en Excel. El CeCo resultante debe existir como Abierta en el Directorio; no se cruza por semejanza de nombres.
Para identificar activos se requiere `STATUS_ EMP (ACTIVO/BAJA)` o `F_BAJA`. `INACTIVO` no se interpreta como `ACTIVO`. Con `F_BAJA`, sólo se incluyen personas sin baja al corte y cuyo ingreso no sea posterior al corte; una fecha de baja inválida o un estatus desconocido se excluye del conteo.
`CORTE DE INFORMACIÓN` seguido de una fecha define el corte de personal. Activos, edades, antigüedad, cumpleaños y aniversarios se calculan a esa fecha, que se muestra en Equipo. Si no existe, se informa que se usó la fecha de construcción.
`NOM_PUESTO`, `SEXO`, `F.NAC` y `F_INGRESO` son opcionales. Sin estos campos, sólo sus métricas quedan vacías. Los promedios usan únicamente personas con la fecha válida; el porcentaje de mujeres usa el sexo informado.
Deduplica por identificador de empleado: repeticiones idénticas se cuentan una vez; asignaciones contradictorias se excluyen y se auditan. El JSON público sólo contiene resúmenes por tienda, sin nombres de empleados, identificadores ni fechas individuales de nacimiento.
Perfil, Negocio y Mix conservan sus propios meses disponibles. Mix muestra los meses que efectivamente contienen información; una tienda o un periodo sin datos se presenta vacío, sin convertirlo en cero.
Checklist antes de publicar
```bash
python scripts/check_file_sizes.py
python scripts/build_data.py
python -m unittest discover -s tests -v
```
El resultado aceptable es: cero errores bloqueantes, archivos menores a 25 MB y todas las pruebas en `OK`. Las advertencias son trazables en `data/audit.json`.
En GitHub, selecciona **Settings → Pages → Build and deployment → Source: GitHub Actions** y ejecuta **Validar y publicar Perfil de Tienda**. Así se publica el artefacto validado de `dist`, sin depender de los JSON antiguos guardados en la rama. No selecciones publicación directa desde una rama.
