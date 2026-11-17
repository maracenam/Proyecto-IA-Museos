# Sprint 1 — Extracción

17 de noviembre de 2026

## Resultado

| Criterio de aceptación | Resultado |
|---|---|
| Registros cargados = total informado por SURDOC (menos cuarentena) | ✅ 77 de 77, 0 en cuarentena |
| Re-ejecutar no duplica | ✅ 2.ª corrida: 0 nuevas o cambiadas, 77 sin cambios; mismas filas y fechas de extracción |
| Pruebas en verde | ✅ 72 pruebas (pytest) y ruff sin observaciones |

Corridas reales contra SURDOC, base local (`docker compose`):

| Corrida | Duración | Solicitudes | Nuevas o cambiadas | Sin cambios | Cuarentena | Bajas |
|---|---|---|---|---|---|---|
| 1 (base vacía) | 2 min 45 s | 83 | 77 | 0 | 0 | 0 |
| 2 (repetición) | 2 min 44 s | 83 | 0 | 77 | 0 | 0 |

83 solicitudes = 1 `robots.txt` + 5 páginas de listado (la 5.ª vacía marca el fin) + 77 fichas, a una cada 2 s.

Contenido cargado: 77 filas en `registros_raw` y `registros`, 119 en `registro_terminos` (objeto: 38 AAT, 32 Tesauro Regional, 6 sin enlace; material: 35 AAT, 3 Tesauro Regional; técnica: 3; nombre alternativo: 2). 41 fichas sin técnica/material, 1 sin objeto (`16-972`), todas con imagen.

## Cómo se usa

```bash
docker compose up -d
cp .env.example .env            # ajustar DATABASE_URL y SURDOC_USER_AGENT
uv run python -m pipeline.run --museo 16                 # todo el museo
uv run python -m pipeline.run --museo 16 --limite 5      # prueba corta (no marca bajas)
```

Para cargar en Supabase basta con apuntar `DATABASE_URL` a la cadena de conexión del proyecto (Settings → Database → Connection string, modo *Session pooler*). Esa cadena lleva la contraseña de la base: va en `.env` o en los secrets de GitHub, nunca en el repositorio.

## Qué se construyó

| Módulo | Qué hace |
|---|---|
| `pipeline/extract/cliente.py` | HTTP con pausa mínima de 2 s (no configurable por debajo), User-Agent obligatorio, reintentos con espera creciente ante errores de red, 429 y 5xx (respeta `Retry-After`), sin reintentar 4xx |
| `pipeline/extract/robots.py` | Evaluador de `robots.txt` con comodines (`*`, `$`) según RFC 9309 |
| `pipeline/extract/listado.py` | Recorre el buscador por páginas hasta una vacía y lee el total informado |
| `pipeline/parse/modelos.py` | Modelo Pydantic `Ficha` (inmutable, campos extra prohibidos) y hash de los campos parseados |
| `pipeline/parse/ficha.py` | HTML → `Ficha`: campos por clase `field--name-*`, bloque de objeto, pares técnica/material, imágenes con crédito |
| `pipeline/extract/extraccion.py` | Orquesta: listado → descarga → parseo → hash → bronce/plata, cuarentena, bajas y `ejecuciones` |
| `pipeline/db.py` | Escrituras idempotentes (upsert), cada ficha en su propia transacción |
| `pipeline/run.py` | `python -m pipeline.run --museo 16` |

Reglas de negocio implementadas:

- **Incremental:** se compara el hash de los campos parseados; si no cambió, solo se actualiza `fecha_ultima_vista`.
- **Cuarentena:** una ficha que falla al descargar (tras los reintentos) o al parsear se guarda en `cuarentena` con el error y el HTML, y el lote sigue.
- **Bajas:** las fichas que desaparecen del listado se marcan `dado_de_baja` sin borrarse, y se reactivan si vuelven. **Solo se marcan bajas si el listado está completo** (mismo número que el total de SURDOC) y la corrida no usa `--limite`: un listado parcial por un error de red no debe dar de baja fichas.
- **Nombre de sitio:** se guarda en bronce (`registros_raw.campos`, privada por RLS) y no existe como columna en plata.

## Hallazgos y cambios durante el sprint

1. **Dos fallos reales detectados por las pruebas** antes de tocar SURDOC:
   - La ficha `16-972` (sin "Objeto") no tiene `a.record-title` en el listado, solo el enlace "Ver". Se habría perdido, el listado habría quedado en 76 de 77 y la protección contra listados incompletos habría bloqueado las bajas en cada corrida. El listado ahora toma cualquier enlace `/registro/…` de la tarjeta.
   - `urllib.robotparser` de Python no entiende comodines a mitad de ruta, así que la regla real `Disallow: /registro/*/pdf` no se habría respetado. Se reemplazó por un evaluador propio, probado con el `robots.txt` real.
2. **Varios materiales en un mismo par.** `16-919` trae "Piedra, Cuero (material animal)" en un solo `technical-item`. Se agregó la columna `registro_terminos.grupo` (migración `004_grupo_terminos.sql`, aplicada también en Supabase) para saber qué técnica va con qué material; `orden` sigue siendo correlativo por campo.
3. **Ficha sin imagen:** como no existe ninguna en Magallanes, la prueba genera el caso quitando el carrusel de una ficha real (`tests/test_parser.py::test_ficha_sin_imagen`).
4. **Técnica/Material con un solo segmento** ("Piedra") se interpreta como material. Es lo que muestran las 36 fichas con el campo; si aparece un caso con solo técnica habrá que distinguirlo con el vocabulario en el Sprint 2.

## Pendiente

- Cargar los datos en Supabase: requiere la cadena de conexión (ver "Cómo se usa").
- La ejecución programada cada 3 días en GitHub Actions es del Sprint 5.
