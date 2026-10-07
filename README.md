# Perfil de Tienda · Remaster operativo

Dashboard estático para GitHub Pages construido con datos reales y un pipeline Python auditable. Los motores se validan por separado, se cruzan únicamente con llaves verificables y pueden aumentar o disminuir filas, CeCos y meses sin cambiar el código.

La vista separa el perfil jerárquico de los indicadores. El selector cambia entre Tienda, DM y Región; cada nivel recalcula responsable, portafolio, equipo, venta e indicadores sin listas fijas.

## Motores independientes

| Motor | Llave o cruce | Uso |
|---|---|---|
| `Directorio_Perfil Tienda.csv` | `CC` | Universo oficial, nombres y filtros |
| `Base_Perfil Tienda.xlsx` | `MES_NUM + CeCo` | Partner, Cliente y parte de Negocio |
| `Base_Perfil Tienda.csv` | `Mes + Tiendas` | Negocio AA |
| `Base_Perfil Tienda_2.csv` | `Mes + Tiendas` | Negocio real, presupuesto y Ticket Real/AA/PPTO |
| `mix/*.csv` | nombre exacto único del Directorio | Mix de producto y orden |
| `Query.xlsx` | `cc + NUM_EMP` | Resumen de partners activos |

`MES_NUM` acepta `1..12` (`1 = Enero`), `YYYYMM` o la etiqueta histórica `1_ene`. El periodo visible se deriva de los motores; no hay listas fijas de CeCos. Un valor porcentual `-100%` se presenta en blanco. Los cruces no encontrados también quedan en blanco y se registran en `data/audit.json`.

## Actualización segura

1. Sustituye sólo el motor actualizado conservando su nombre y encabezados.
2. Si actualizas Mix, colócalo fuera del repositorio y ejecuta:

   ```bash
   python scripts/split_mix.py --source "/ruta/Base_Mix.csv" --output "data/engines/mix"
   ```

3. Ejecuta:

   ```bash
   python scripts/check_file_sizes.py
   python scripts/build_data.py
   python -m unittest discover -s tests -v
   ```

4. Revisa `data/audit.json`. Los errores bloquean la publicación; las advertencias identifican datos reales sin cruce y no fabrican valores.
5. Publica. GitHub Actions repite las validaciones y sólo despliega los archivos mínimos del sitio; nunca publica motores crudos.

Consulta [data/engines/INSTRUCCIONES_ACTUALIZACION.md](data/engines/INSTRUCCIONES_ACTUALIZACION.md) para el contrato detallado de cada archivo.

## Lectura operativa

- Cada tarjeta muestra Real, AA/PPTO y `Real - referencia`.
- Ticket muestra simultáneamente Real, AA y PPTO. VMT y OMT se presentan en Negocio.
- El botón `Tendencia / Brecha` cambia todas las gráficas; cada punto muestra su valor mensual.
- Venta se presenta en millones de pesos y conserva escala automática.
- El mes sólo se filtra dentro de Mix; los indicadores muestran el acumulado y la tendencia completa.
- Verde: resultado favorable. En Labor, Costo, Rotación y DT, menor es mejor.
- DT se normaliza a segundos y se presenta `mm:ss`; `01:15` representa un minuto con quince segundos.
- YTD de Rotación toma el último mes disponible; Venta suma; las demás métricas promedian los periodos disponibles.
- Las gráficas recalculan mínimo, máximo y separación según los valores visibles.

## Vista local

```bash
python scripts/build_data.py
python scripts/build_exports.py
python -m http.server 8000
```

Abre `http://localhost:8000`.

## Limpieza del proyecto anterior

El workflow **Eliminar archivos legados autorizados** se ejecuta al actualizar su script o manifiesto, al reintroducir un legado y después de una publicación correcta en `main`. También puede ejecutarse desde Actions de forma manual.

Python revisa las dependencias de HTML, JavaScript, CSS, manifest y los motores antes de retirar únicamente las rutas de `scripts/obsolete-files.json`. Bloquea archivos todavía referenciados, rutas fuera del proyecto, directorios y enlaces simbólicos. Si falla una retirada, revierte las anteriores.

El workflow reconstruye los datos y exportaciones, ejecuta las pruebas y prepara el sitio mínimo antes de registrar las eliminaciones. Sólo incluye archivos eliminados en su commit y cancela si `main` cambia durante la validación. Actions muestra cuántos archivos se retiraron; una ejecución sin legados presentes conserva el repositorio.

Comprobación local: `python scripts/cleanup_obsolete.py --check-clean`. Aplicación local: `python scripts/cleanup_obsolete.py --apply --check-clean`. El despliegue también retira los legados de su copia de trabajo antes de generar el artefacto publicado.

La limpieza incluye los archivos históricos de raíz `Store_Master_Audit.csv`, `data.js`, `README.txt`, `manifest.json`, `style.css` y los iconos duplicados. Conserva `styles.css`, `manifest.webmanifest` y `assets/`.
