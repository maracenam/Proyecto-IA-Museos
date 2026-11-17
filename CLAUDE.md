# CLAUDE.md — Observatorio de Colecciones Arqueológicas SURDOC

Contexto para Claude Code. Léelo completo antes de escribir código. El diseño técnico detallado está en `DISENO_TECNICO.md`; este archivo explica el porqué de las decisiones, lo que ya sabemos de SURDOC y cómo trabajar. Los hallazgos del Sprint 0 están en `docs/sprint0.md`.

Responde y comenta en español. Los nombres de código (variables, funciones, tablas) también en español, salvo términos técnicos establecidos (hash, embedding, pipeline).

---

## 1. Qué es el proyecto y para qué existe

Un pipeline de datos que toma las fichas arqueológicas públicas de SURDOC (el sistema de registro de colecciones de los museos del Estado de Chile), las estructura, las normaliza con ayuda de IA y las expone en un dashboard con búsqueda en lenguaje natural.

**Objetivo de negocio:** es una pieza de portafolio. La meta es vender soluciones de datos e IA a consultoras arqueológicas chilenas. El proyecto debe demostrar el ciclo completo "datos desordenados → IA → información confiable y consultable", usando solo datos públicos. Por eso la **credibilidad ante arqueólogos** pesa más que la cantidad de funcionalidades: trazabilidad, revisión humana y métricas de calidad publicadas son parte central del producto, no adornos.

**Antecedente:** el equipo ya hizo un proyecto gratuito para el Museo Regional de Magallanes (repo `Crisxpy/museo-magallanes-3d`): un visor 3D en Next.js + Supabase + Vercel que combina modelos de Sketchfab con fichas de SURDOC, con un scraper de fichas ("prescrapper"). La lógica de scraping de ese proyecto se reutiliza aquí.

**Feedback real de una arqueóloga (guía el roadmap futuro, no este MVP):** en terreno se trabaja en papel; los dibujos se escanean y suben a un Drive; las fichas dependen del formato de cada consultora; los informes los redacta una persona dedicada. El dolor está en consolidar datos atrapados en escaneos. Un proyecto futuro de "escaneo a datos" se apoyará en lo que se construya aquí.

---

## 2. Decisiones tomadas (no reabrir sin preguntar)

| Decisión | Motivo |
|---|---|
| **Sin costos externos por ahora** | Requisito explícito. Todo en planes gratuitos y modelos locales. |
| **IA local en el PC propio** con Ollama (LLM) y sentence-transformers (embeddings) | Cero costo y "los datos no salen de tu infraestructura", argumento de venta para consultoras con datos privados. |
| **El modelo de lenguaje es intercambiable** por variable de entorno | Si un cliente paga por más calidad, se cambia a una API sin tocar el resto. Diseña una interfaz `Normalizador` con implementación Ollama. |
| **Extracción en GitHub Actions cada 3 días** | Gratis; mantiene activa la base de Supabase (el plan gratis pausa tras 7 días sin actividad). |
| **Normalización y embeddings en el PC**, manual o con cron, procesando pendientes | GitHub Actions no tiene GPU. Si el PC está apagado, las fichas esperan; la extracción nunca se bloquea por eso. |
| **Supabase** (Postgres + pgvector + Auth + RLS) | Ya conocido del proyecto anterior; datos y vectores en una sola base. |
| **Streamlit** para la web (por ahora) | Todo en Python, rápido de construir. Vercel + Next.js queda como opción futura; solo cambiaría la capa web. |
| **MVP = Museo Regional de Magallanes**, clasificación Antropología, Arqueología y Etnografía | Alcance acotado para tener algo mostrable pronto. |
| **Se normalizan solo 3 campos**: tipo de objeto, material/técnica, estado de conservación | Datación y atribución cultural requieren criterio experto; un error ahí dañaría la credibilidad. Cultura y Área geográfica se guardan pero no se normalizan. |

---

## 3. Lo que ya sabemos de SURDOC (verificado sobre HTML real)

Inicialmente se analizó la ficha `/registro/24-4` ("Mesa ratona") y la portada. En el Sprint 0 se verificó sobre las **77 fichas reales** de Magallanes (detalle en `docs/sprint0.md`).

**Identificadores**

- URL de ficha: `https://www.surdoc.cl/registro/{institucion}-{numero}`. El prefijo es el código de institución.
- Museo Regional de Magallanes = institución **16**.
- Clasificación Antropología, Arqueología y Etnografía = **548** (Arte = 549, Historia = 550).

**Buscador (base para el listado)** — verificado en Sprint 0

- `GET https://www.surdoc.cl/colecciones?f[0]=institution:16&first_level_classification=548&query=&page={n}`.
- Paginación con `page=0..N`, **21 fichas por página**. Una página fuera de rango devuelve 0 fichas (condición de término).
- El total aparece como texto "77 registros" y en `data-drupal-facet-item-count` de la faceta de institución.
- Cada resultado: `div.views-row` con `a.record-title[href="/registro/16-…"]`.
- La miniatura del listado **no es fiable** para saber si una ficha tiene imagen.

**Estructura de la ficha (Drupal)**

- Campos simples: `div.field.field--inline` con `div.field-label` (etiqueta) y `div.field-item` (valor). Algunos tienen varios `div.field-item`. La clase `field--name-*` es un identificador estable del campo (ej. `field--name-conservation-state`).
- Bloque de objeto `div.field--name-object`: varios `div.form-item`, cada uno con `label.form-item__label` + `div.field-item` (Objeto, Nombre alternativo, Dimensiones, Técnica / Material, Ubicación, Situación).
- **Técnica / Material**: cada valor es un `div.technical-item` con la forma `técnica - material`, cada parte con su propio enlace (ej. "Tallado - Madera", "Ahuecar - Madera"). A veces solo viene el material ("Piedra") y a veces varios materiales separados por coma (`16-919`: "Piedra, Cuero (material animal)"; se guardan con el mismo `grupo`).
- **Listado:** una ficha sin "Objeto" (`16-972`) no trae `a.record-title`; tomar cualquier enlace `/registro/…` de la tarjeta.
- **robots.txt** usa comodines (`/registro/*/pdf`): `urllib.robotparser` no los entiende; usar `pipeline/extract/robots.py`.
- Etiquetas encontradas en Magallanes: Institución, Número de registro, Nº de inventario, Clasificación, Colección, Objeto, Nombre alternativo, Dimensiones, Técnica / Material, Ubicación, Situación, Descripción, Estado de conservación, Adquisición, Forma de ingreso, Fecha de ingreso, Registradores, Área geográfica, Área cultural primer nivel, Área cultural segundo nivel, Cultura originaria, Cultura arqueológica, Procedencia, Nombre sitio, Historia del objeto, Historia de propiedad y uso. (No existe una etiqueta "Cultura" a secas.)
- Imágenes: carrusel `a.litebox` con `href` a `/sites/default/files/record_images/*.jpg` (antiguas) **o** `/sites/default/files/records/images/AAAA-MM/*.jpg` (nuevas). El `alt`/`title` del `img` trae el **crédito del fotógrafo** (puede venir vacío en algunas imágenes).

**Vocabularios enlazados: AAT y Tesauro Regional**

- Objeto, Técnica y Material enlazan a términos del **AAT en español** (`https://www.aatespanol.cl/terminos/300039757`) **o del Tesauro Regional Patrimonial** (`https://www.tesauroregional.cl/terminos/384`, a veces con `http://`). En Magallanes, Objeto: 38 AAT, 32 Tesauro Regional, 6 sin enlace.
- Un campo puede tener **varios valores**, cada uno con su enlace.
- Extrae siempre el **texto, la fuente (aat / tesauro_regional) y el ID** de cada valor. La normalización va primero por ID, luego por reglas/sinónimos, y solo al final por LLM.

**Trampa: atributos dinámicos**

- El HTML trae atributos que pueden cambiar entre descargas (`data-once`, `data-b-token`, `itok=` de imágenes, etc.). **Nunca hashees el HTML**: hashea los campos ya parseados y normalizados en un orden estable. Si no, la actualización incremental reprocesaría todo siempre.

**Calidad del dato (Sprint 0)**

- 41 de 77 fichas no traen Técnica / Material: el material muchas veces solo está en la Descripción ("elaborada en obsidiana").
- Hay inconsistencias reales (ej. `16-872` "Fragmento (cerámica)" con material "Madera").
- Estado de conservación ya viene controlado: Muy bueno / Bueno / Regular.
- Una ficha (`16-989`) trae **Nombre sitio**: se guarda, pero nunca se publica (protección de sitios).

---

## 4. Reglas que no se negocian

- **Respeto a la fuente:** revisar `robots.txt` y términos de uso en el Sprint 0, antes de cualquier extracción masiva. Máximo 1 solicitud cada 2 segundos, User-Agent identificable con contacto, reintentos con espera creciente.
- **Protección de sitios arqueológicos:** nunca publicar coordenadas ni ubicaciones exactas (incluido "Nombre sitio"). Agregar por región, comuna o área geográfica.
- **Fotografías:** no descargarlas ni republicarlas. Si la app muestra una miniatura, cargarla desde SURDOC con el crédito del fotógrafo y enlazar a la ficha original.
- **Trazabilidad:** el valor original nunca se sobrescribe. Cada valor normalizado registra método (AAT, sinónimo, LLM), modelo, versión de prompt y confianza.
- **Las revisiones humanas mandan:** se guardan en su propia tabla y prevalecen sobre cualquier versión de prompt (vista `valor_vigente`).
- **Seguridad:** secretos solo en variables de entorno o secrets (GitHub, Streamlit), nunca en el repo. RLS en Supabase: lectura pública, escritura solo para el revisor autenticado y para el pipeline con su propia clave.
- **Idempotencia:** volver a ejecutar cualquier etapa no duplica datos.
- **Errores aislados:** una ficha que falla al parsear va a `cuarentena` y no detiene el lote.

---

## 5. Cómo trabajar

- **Por sprints**, en el orden de `DISENO_TECNICO.md`. No adelantes trabajo de sprints futuros sin preguntar.
- Antes de cada sprint, resume en pocas líneas qué vas a construir y confirma. Al cerrar, verifica los criterios de aceptación ejecutando el código, no solo leyéndolo.
- **Verifica corriendo:** pruebas con `pytest`, estilo con `ruff`. El parser se prueba con fichas HTML guardadas en `tests/fixtures/`.
- Ramas `feat/...` y `fix/...`, commits con prefijo convencional (`feat:`, `fix:`, `docs:`), etiqueta de versión al cerrar cada sprint (`v0.1`, `v0.2`...).
- Dependencias con `uv`. Entorno local con `docker compose` (Postgres y, si conviene, Ollama).
- Migraciones SQL versionadas en `db/migrations/`. Prompts versionados en `prompts/`. Vocabularios en `vocab/` como CSV.
- Si algo del diseño resulta impracticable al implementarlo, **dilo y propone el cambio** en vez de improvisar. Si cambia una decisión, actualiza `DISENO_TECNICO.md`.

---

## 6. Estado

- **Sprint 0:** completo, ver `docs/sprint0.md`. Supabase: proyecto `observatorio-surdoc` (ref `bksdjmwdvrxwtlniatbm`, `sa-east-1`) con esquema, RLS y permisos aplicados y verificados. Modelo local elegido: `gemma2:2b` (9/10 aciertos, 0,8 s por valor en GPU).
- **Sprint 1:** completo, ver `docs/sprint1.md`. `python -m pipeline.run --museo 16` carga las 77 fichas (bronce y plata) en ~3 min; re-ejecutar no duplica. Datos aún solo en Postgres local: cargar en Supabase requiere la cadena de conexión.

## 7. Decisiones pendientes

- Dashboard en Streamlit, Power BI o ambos.
- Qué museos se suman en el Sprint 5.
- Si la arqueóloga puede validar el vocabulario y la muestra de revisión.
- Si el repositorio es público desde el inicio o al cerrar el MVP.
- Qué categorías del observatorio agrupan los términos AAT / Tesauro Regional (definir con la arqueóloga). Ojo: "textil" vs "fibra vegetal" confundió a los tres modelos probados (cestería).
