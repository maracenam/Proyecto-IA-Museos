# Sprint 0 — Preparación y descubrimiento

17 de noviembre de 2026

Estado del checklist de `CLAUDE.md` §6:

| # | Ítem | Estado |
|---|------|--------|
| 1 | Estructura del repositorio | ✅ Hecho |
| 2 | `robots.txt` y términos de uso | ✅ `robots.txt` revisado; ⚠️ no hay términos de uso publicados (ver abajo) |
| 3 | Listado: paginación y total | ✅ 77 registros, 4 páginas de 21 |
| 4 | 5–10 fichas como fixtures | ✅ 10 fichas (⚠️ ninguna ficha de Magallanes está sin imagen) |
| 5 | Postgres local + migraciones | ✅ `docker compose up -d` aplica las migraciones; probado con pytest |
| 6 | Proyecto en Supabase + pgvector + RLS | ✅ Proyecto `observatorio-surdoc` creado, con RLS activa (falta un ajuste menor, ver §6.1) |
| 7 | Ollama en el PC y comparación de modelos | ✅ Elegido `gemma2:2b`: 9/10 aciertos, 0,8 s por valor, 100 % en GPU (§6.2) |
| 8 | Documentar hallazgos | ✅ Este documento |

---

## 1. `robots.txt` y términos de uso

**`https://www.surdoc.cl/robots.txt`** (Drupal estándar), aplica a `User-agent: *`:

- **Permitido:** `/colecciones` (listado) y `/registro/{id}` (fichas). Las imágenes en `/sites/default/files/` no están bloqueadas, pero igual no se descargan (regla del proyecto).
- **Prohibido y relevante:** `/registro/*/pdf`, `/registro-descarga/*/objectid`, `/search/`. El pipeline no debe usar esas rutas.
- No declara `Crawl-delay`. Se mantiene nuestro límite de 1 solicitud cada 2 segundos.

**Términos de uso:** no se encontró una página de términos, condiciones ni licencia de los datos en el portal (se revisaron el menú, el pie de página, "¿Quiénes somos?" y las fichas). El único canal es `contacto@cdbp.gob.cl` (Centro de Documentación de Bienes Patrimoniales, SNPC).

**Recomendación:** antes de publicar la app (Sprint 3), escribir a ese correo describiendo el proyecto (uso no comercial de datos públicos, atribución a SURDOC y la institución, sin republicar fotografías, enlace a cada ficha) y guardar la respuesta. Nada de lo revisado impide extraer los 77 registros con el ritmo definido.

**User-Agent:** se usa `ObservatorioSURDOC/0.1 (+https://github.com/maracenam/Proyecto-IA-Museos)`. Si el repositorio sigue privado, conviene cambiar la URL por un correo de contacto del proyecto (variable `SURDOC_USER_AGENT`).

## 2. Listado y paginación

URL de listado (se puede reproducir en el navegador):

```
https://www.surdoc.cl/colecciones?f%5B0%5D=institution%3A16&first_level_classification=548&query=&page={n}
```

- **Total: 77 registros** (texto "77 registros" y `data-drupal-facet-item-count="77"` en la faceta Institución).
- **21 fichas por página**, `page=0` a `page=3` (21 + 21 + 21 + 14 = 77, sin repetidos). `page=4` devuelve 0 fichas: sirve como condición de término, más robusta que leer el paginador.
- Cada resultado es un `div.views-row` con `a.record-title[href="/registro/16-…"]`.
- Subclasificaciones (facetas): Utensilios, Herramientas y Equipos (65), Textil, Vestuario y Adornos (6), Otros (6).
- Situación del objeto: 76 "Existente"; una ficha no trae ese dato.
- El orden es por número de registro como texto (`16-1002` antes de `16-447`). El extractor no debe depender del orden.

**Criterio de aceptación del Sprint 1:** 77 registros cargados (menos los que queden en cuarentena).

Que el MVP tenga solo 77 fichas es una buena noticia para la calidad (se puede revisar el 100 % a mano), pero achica la demostración. Conviene adelantar a Sprint 5 la decisión de qué museos se suman. El filtro de instituciones del buscador lista 45 instituciones (no todas tienen colecciones arqueológicas).

## 3. Estructura de las fichas (verificada sobre las 77)

Se hizo un censo de las 77 fichas (descargadas a 1 req / 2 s, solo para análisis; en el repo quedan 10 como fixtures).

| Etiqueta | Fichas (de 77) |
|---|---|
| Institución, Nº de registro, Nº de inventario, Clasificación, Colección, Descripción, Estado de conservación, Registradores | 77 |
| Objeto (bloque de objeto) | 76 |
| Dimensiones | 75 |
| Ubicación | 74 |
| Adquisición / Forma de ingreso | 50 |
| **Técnica / Material** | **36** |
| Historia de propiedad y uso | 4 |
| Área geográfica | 3 |
| Fecha de ingreso | 3 |
| Situación, Nombre alternativo, Historia del objeto, Área cultural (1.º y 2.º nivel) | 2 |
| Cultura originaria, Cultura arqueológica, Procedencia, **Nombre sitio** | 1 |

Hallazgos que corrigen o precisan lo que sabíamos:

1. **Dos vocabularios, no solo AAT.** Objeto, Técnica y Material enlazan al AAT en español (`aatespanol.cl/terminos/{id}`) **o** al Tesauro Regional Patrimonial (`tesauroregional.cl/terminos/{id}`, a veces con `http://`).
   - Objeto: 38 AAT, 32 Tesauro Regional, 6 sin enlace.
   - Técnica / Material: 37 enlaces AAT, 3 Tesauro Regional (ej. "Obsidiana" → Tesauro Regional 3696).
   → `registro_terminos` guarda `fuente_termino` + `id_termino` en vez de solo `aat_id` (cambio aplicado en el modelo de datos).
2. **Técnica / Material viene en pares.** Cada valor es un `div.technical-item` con `técnica - material`, cada parte con su enlace; a veces solo el material ("Piedra"). Solo una ficha (`16-447`) trae dos pares ("Tallado - Madera", "Ahuecar - Madera"). Se guardan como filas `tecnica` y `material` con el mismo `orden`.
3. **41 de 77 fichas (53 %) no tienen Técnica / Material.** El material suele estar solo en la Descripción ("Objeto lítico…", "Tejida con junquillo", "hecho de huesos de ballena"). **Implicancia para el Sprint 2:** la normalización de material no puede depender solo de reglas por ID; el LLM tendrá que inferirlo desde la descripción en más de la mitad de los casos. Propuesta: que esos valores se marquen con un método propio (`llm_descripcion`) y vayan siempre a revisión en la primera ronda.
4. **Hay inconsistencias reales**, buen material para demostrar la revisión humana: `16-872` "Fragmento (cerámica)", descrito como "fragmento cerámico", tiene material "Madera" (AAT 300011914).
5. **Estado de conservación ya está controlado:** solo "Bueno" (54), "Regular" (17) y "Muy bueno" (6). Se normaliza con una tabla fija; no necesita LLM.
6. **No existe la etiqueta "Cultura".** Vienen "Cultura originaria", "Cultura arqueológica" y "Área cultural primer/segundo nivel" (campos casi vacíos en Magallanes). Se guardan en columnas separadas en `registros`.
7. **Nombre sitio (`16-989`: "Rey Felipe") y texto libre con sitios.** El campo `field--name-archa-site-name` se guarda solo en bronce (privado) y no pasa a `registros`. Además, "Historia del objeto" de `16-872` menciona el sitio en texto libre: **antes de publicar campos de texto libre en la app (Sprint 3) hay que decidir si se muestran o se omiten.**
8. **Imágenes en dos rutas:** `/sites/default/files/record_images/*.jpg` (antiguas) y `/sites/default/files/records/images/AAAA-MM/*.jpg` (nuevas). El crédito está en `img[title]`/`img[alt]` dentro de `a.litebox` y a veces viene vacío. **La miniatura del listado no es fiable:** 32 fichas aparecen sin imagen en el listado, pero las 77 tienen al menos una imagen en la ficha.
9. **Identificadores estables por clase CSS:** cada campo trae `field--name-*` (ej. `field--name-conservation-state`, `field--name-physical-description`, `field--name-archa-site-name`). Conviene que el parser use estas clases, más estables que el texto de la etiqueta.
10. **Atributos dinámicos:** el HTML trae `data-b-token`, `data-once` e `itok=`. Dos descargas seguidas de `16-447` resultaron idénticas (probablemente caché), pero se mantiene la regla de hashear los campos parseados y nunca el HTML.

## 4. Fixtures (`tests/fixtures/`)

| Archivo | Por qué |
|---|---|
| `registro_16-447.html` | Dos pares técnica/material, Nombre alternativo, Cultura originaria, Área cultural, Área geográfica, 5 imágenes (una sin crédito) |
| `registro_16-989.html` | Nombre sitio (dato sensible), Cultura arqueológica, Procedencia |
| `registro_16-872.html` | Inconsistencia cerámica/madera, Objeto sin enlace, sitio en texto libre |
| `registro_16-1005.html` | Material enlazado al Tesauro Regional (Obsidiana) |
| `registro_16-1002.html` | Objeto en Tesauro Regional + material AAT |
| `registro_16-1771.html` | Objeto AAT, sin Técnica/Material, imagen en la ruta nueva |
| `registro_16-3570.html` | Campo Situación en el bloque de objeto, varias imágenes |
| `registro_16-924.html` | Objeto sin enlace, sin Técnica/Material |
| `registro_16-907.html` | Caso simple: objeto y material AAT |
| `registro_16-3366.html` | Subclasificación Textil, Vestuario y Adornos |
| `listado_548_16_p0.html`, `listado_548_16_p3.html` | Primera y última página del listado |

**Fichas "sin imagen" y "con varios materiales":** no hay ninguna ficha de Magallanes sin imagen, y la única con varios valores es `16-447` (mismo material, dos técnicas). Para probar el caso "sin imagen" en el Sprint 1 propongo una de dos opciones: (a) descargar una ficha sin imagen de otro museo, o (b) generar una variante de una fixture quitando el carrusel, marcada como sintética.

## 5. Base de datos local

- `docker compose up -d` levanta `pgvector/pgvector:pg17` y aplica `db/migrations/*.sql` la primera vez que se crea el volumen.
- Para volver a aplicar desde cero: `docker compose down -v && docker compose up -d`.
- Las migraciones son idempotentes (se pueden correr de nuevo con `psql -f`).
- pgvector se instala en el esquema `extensions`, no en `public` (aviso de seguridad de Supabase). `003_vector_en_extensions.sql` corrige bases creadas antes de este cambio; se probó sobre una base con la extensión en `public`.
- Cambios al modelo de datos respecto del diseño original (ya reflejados en `DISENO_TECNICO.md`):
  - `registro_terminos`: `fuente_termino` (`aat` / `tesauro_regional`) + `id_termino` en vez de `aat_id`.
  - `vocabulario`: clave `campo` + `fuente_termino` + `id_termino`.
  - `registros`: `cultura_originaria`, `cultura_arqueologica`, `area_cultural` y `coleccion` en vez de un solo campo "cultura". El nombre de sitio no pasa a plata.
  - Nueva tabla `revisores` (lista de usuarios autorizados). Sin ella, cualquier persona que se registrara en Supabase Auth podría escribir revisiones.
  - La vista `valor_vigente` se deja para el Sprint 3, como indica el plan.
- **RLS** (`002_rls.sql`): lectura pública de plata, oro y referencia; bronce y `revisores` privados; solo un usuario presente en `revisores` puede insertar en `revisiones`, y solo a su nombre. El pipeline escribe con la conexión del dueño de las tablas (en Supabase, la cadena de conexión de la base o `service_role`), que no se usa nunca en la app pública.
- `tests/test_migraciones.py` comprueba todo esto contra el Postgres real: tablas, RLS activo, pgvector, idempotencia, que `anon` no lee bronce ni escribe, que un usuario autenticado que no es revisor no puede escribir y que un revisor solo firma con su propio uid.

## 6. Pendientes que requieren tu acción

### 6.1 Supabase (ítem 6)

**Hecho (17-11-2026):** proyecto `observatorio-surdoc` (ref `bksdjmwdvrxwtlniatbm`, región `sa-east-1`, plan gratuito), organización `maracenam`.

| Migración en Supabase | Contenido | Estado |
|---|---|---|
| `001_esquema_inicial` | 11 tablas, pgvector, museo 16 | ✅ |
| `002a_rls_politicas` | RLS en las 11 tablas y todas las políticas de `002_rls.sql` | ✅ |
| `003_vector_en_extensions` | pgvector movido de `public` a `extensions` | ✅ |
| `revoke` de `002_rls.sql` | Quitar los permisos por defecto de `anon`/`authenticated` | ⏳ Pendiente |

La migración 002 se aplicó en dos partes porque la integración pide confirmación para las sentencias `drop`/`revoke`, y esa confirmación expiraba sin respuesta. Mientras faltan los `revoke`, la protección la da RLS: las tablas de bronce (`registros_raw`, `cuarentena`) no tienen políticas, así que `anon` y `authenticated` no ven ni escriben filas, y ninguna tabla tiene política de escritura salvo `revisiones` (solo revisores). Los `revoke` son una defensa adicional. Para terminar, ejecutar en el SQL Editor:

```sql
revoke all on registros_raw, cuarentena, revisores from anon, authenticated;
grant select on revisores to authenticated;
revoke insert, update, delete, truncate on museos, registros, registro_terminos, vocabulario,
    normalizaciones, revisiones, embeddings, ejecuciones from anon, authenticated;
grant insert on revisiones to authenticated;
```

Advisors → Security tras aplicar: solo quedan avisos informativos "RLS enabled, no policy" en `registros_raw` y `cuarentena`, que son intencionales (son privadas).

Pendiente para el Sprint 3 (cola de revisión): en Authentication → Sign In / Providers, **desactivar los registros públicos** (los revisores se invitan a mano) y agregar su uid a la tabla `revisores`.

### 6.2 Ollama (ítem 7)

En tu PC:

```bash
# instalar Ollama desde https://ollama.com y luego:
ollama pull qwen2.5:3b
ollama pull llama3.2:3b
ollama pull gemma2:2b
uv run python scripts/probar_modelos_ollama.py qwen2.5:3b llama3.2:3b gemma2:2b
```

El script usa 10 casos reales de Magallanes (incluido el caso trampa `16-872`), mide aciertos, tiempo por valor y el porcentaje del modelo cargado en GPU, e imprime una tabla Markdown. Pega el resultado aquí abajo y elige el modelo. Las categorías del script son provisorias.

**Resultado (17-11-2026, PC propio `DESKTOP-PKP439S`, Windows):**

| Modelo | Aciertos | JSON inválido | Tiempo mediano / valor | Máximo | GPU |
|---|---|---|---|---|---|
| qwen2.5:3b | 7/10 | 0 | 0,7 s | 1,1 s | 100 % en GPU |
| llama3.2:3b | 7/10 | 0 | 0,7 s | 0,9 s | 100 % en GPU |
| **gemma2:2b** | **9/10** | 0 | 0,8 s | 0,9 s | 100 % en GPU |

**Decisión: `gemma2:2b`** (`LLM_MODELO=gemma2:2b`). Es el que más acierta, resuelve bien el caso trampa (`16-872`: cerámica declarada como madera; llama3.2 cae en él) y es el más pequeño. Los tres caben enteros en la GPU y tardan menos de 1 s por valor: normalizar las 77 fichas toma alrededor de un minuto, así que la velocidad no es un problema.

Lecturas para el Sprint 2:

- **Los tres fallan `16-1073`** (canasto tejido con junquillo): responden "textil" en vez de "fibra vegetal". No es un error del modelo sino una ambigüedad del vocabulario: "textil" mezcla material y técnica. Las categorías deben definirse con la arqueóloga (¿material = fibra vegetal y técnica = cestería?) antes de escribir el prompt definitivo.
- **La confianza que reporta el LLM no sirve tal cual:** llama3.2 dio 0,9 a respuestas equivocadas y qwen2.5 dio 1,0 a un error. Confirma que el umbral debe calibrarse contra la muestra revisada a mano y no usarse en bruto.
- **Muestra pequeña:** 10 casos alcanzan para descartar modelos y medir velocidad, no para estimar la precisión real. Esa medición (50 valores por campo) es parte del Sprint 2.

## 7. Cómo verificar este sprint

```bash
cp .env.example .env
docker compose up -d
uv sync
uv run ruff check . && uv run ruff format --check .
DATABASE_URL=postgresql://observatorio:observatorio@localhost:5432/observatorio uv run pytest
```

Resultado en el entorno de desarrollo: 24 pruebas en verde y ruff sin observaciones.
