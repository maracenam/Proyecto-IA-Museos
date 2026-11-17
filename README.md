# Observatorio de Colecciones Arqueológicas SURDOC

Pipeline que convierte las fichas arqueológicas públicas de [SURDOC](https://www.surdoc.cl) en un dataset normalizado, consultable y trazable, con un dashboard y búsqueda en lenguaje natural. La IA corre en local (Ollama), sin costos externos.

- Diseño técnico: [`DISENO_TECNICO.md`](DISENO_TECNICO.md)
- Contexto y reglas del proyecto: [`CLAUDE.md`](CLAUDE.md)
- Hallazgos del Sprint 0: [`docs/sprint0.md`](docs/sprint0.md)
- Extracción (Sprint 1): [`docs/sprint1.md`](docs/sprint1.md)
- Normalización (Sprint 2): [`docs/sprint2.md`](docs/sprint2.md)
- Dashboard y revisión (Sprint 3): [`docs/sprint3.md`](docs/sprint3.md)

## Estado

| Sprint | Objetivo | Estado |
|---|---|---|
| 0 | Preparación y descubrimiento | Completo (modelo local: gemma2:2b) |
| 1 | Extracción | Completo: 77/77 fichas, re-ejecución sin duplicados ([detalle](docs/sprint1.md)) |
| 2 | Normalización | Código listo; falta la corrida con gemma2:2b y la muestra revisada ([detalle](docs/sprint2.md)) |
| 3 | Dashboard y revisión (MVP) | App lista y probada; falta desplegarla en Streamlit Cloud ([detalle](docs/sprint3.md)) |
| 4 | Búsqueda semántica | — |
| 5 | Escala y portafolio | — |

MVP: Museo Regional de Magallanes, clasificación Antropología, Arqueología y Etnografía (77 fichas).

## Desarrollo local

Requisitos: Docker y [uv](https://docs.astral.sh/uv/).

```bash
cp .env.example .env
docker compose up -d          # Postgres + pgvector con las migraciones aplicadas
uv sync                       # dependencias (Python 3.12)
uv run ruff check .
DATABASE_URL=postgresql://observatorio:observatorio@localhost:5432/observatorio uv run pytest
uv run python -m pipeline.run --museo 16   # extrae las 77 fichas (~3 min)
uv run python -m pipeline.normalize correr # reglas + LLM local (LLM_MODELO)
uv run streamlit run app/app.py            # app: colección, revisión y método
```

Ollama, opcional en local: `docker compose --profile ia up -d`.

## Fuente y atribución

Los datos provienen de SURDOC (Servicio Nacional del Patrimonio Cultural) y de cada institución. Cada registro enlaza a su ficha original. Las fotografías no se descargan ni se republican, y nunca se publican sitios arqueológicos ni ubicaciones exactas.
