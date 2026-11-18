# Sprint 4 — Búsqueda semántica

18 de noviembre de 2026 · **Estado: listo y verificado en local; falta generar los embeddings en Supabase y comprobar la memoria en Streamlit Cloud.**

## Criterios de aceptación

| Criterio | Estado |
|---|---|
| Diez consultas de prueba devuelven resultados pertinentes en los primeros cinco | ✅ 10/10 con el modelo real, a través de la misma función SQL que usa la app, como usuario anónimo |
| La app desplegada carga el modelo sin exceder la memoria | 🟡 En local la app con el modelo cargado usa ~1,0 GB (pico 1,03 GB). Falta confirmarlo en Streamlit Cloud al desplegar |

## 1. Modelo elegido

Se compararon dos modelos multilingües pequeños de sentence-transformers sobre las 77 fichas y las 10 consultas de `evaluacion/consultas_busqueda.csv`:

| Modelo | Consultas con acierto en el top 5 | Precisión@5 media | Dimensión | Codificar 77 fichas (CPU) |
|---|---|---|---|---|
| **intfloat/multilingual-e5-small** | **10/10** | **0,68** | 384 | 3,4 s |
| paraphrase-multilingual-MiniLM-L12-v2 | 10/10 | 0,58 | 384 | 0,9 s |

**Decisión: `intfloat/multilingual-e5-small`** (`EMBEDDING_MODELO`). Está entrenado para búsqueda (usa prefijos `query:` / `passage:`) y ordena mejor raspadores, puntas de obsidiana y boleadoras. La precisión@5 tiene techo bajo en consultas con pocas fichas pertinentes (la canoa es una sola), así que lo relevante es que las 10 encuentran algo pertinente arriba.

Resultado por consulta (modelo elegido, función `buscar_fichas` como `anon`):

| Consulta | Pertinentes en el top 5 |
|---|---|
| instrumento de piedra para raspar cueros | 5/5 |
| arma arrojadiza con piedras atadas para cazar | 1/5 |
| cestería tejida con fibras vegetales | 5/5 |
| piezas de hueso de ballena para pescar | 5/5 |
| embarcación de los pueblos canoeros | 1/1 |
| puntas de proyectil talladas en obsidiana | 2/3 |
| recipientes de vidrio | 4/5 |
| adornos de metal | 5/5 |
| arco y flechas de madera | 5/5 |
| prenda de vestir o tejido de lana | 1/2 |

La más débil es "arma arrojadiza con piedras atadas": encuentra una boleadora primero, pero luego trae guaicas y un proyectil (también armas). Mejoraría cuando gemma2:2b complete las categorías de material, que entran en el texto de cada ficha.

## 2. Qué se construyó

| Pieza | Qué hace |
|---|---|
| `pipeline/embed/codificador.py` | Interfaz `Codificador` e implementación con sentence-transformers (CPU), con los prefijos de E5 |
| `pipeline/embed/proceso.py` | Texto de cada ficha (solo campos públicos: objeto, categorías vigentes, técnica/material, cultura, área cultural, colección, descripción), generación incremental por hash del texto, búsqueda y evaluación |
| `python -m pipeline.embed generar \| evaluar` | Línea de comandos (se corre en el PC, como la normalización) |
| `db/migrations/007_busqueda_semantica.sql` | `embeddings.hash_texto` y la función `buscar_fichas(vector, modelo, limite)` con `security invoker` (aplicada en Supabase) |
| `app/buscar.py`, `app/busqueda.py` | Página **Buscar**: consulta libre o de ejemplo, 10 resultados con tipo/material y su validación, extracto de la descripción, foto desde SURDOC con crédito y enlace a la ficha |
| `evaluacion/consultas_busqueda.csv` | Las 10 consultas de prueba y sus fichas pertinentes |

Decisiones de seguridad y trazabilidad:

- **El texto indexado solo usa campos públicos.** La tabla `embeddings` es de lectura pública, así que nunca incluye el nombre de sitio ni los textos de historia (probado con `16-989`).
- **Cada vector guarda su modelo** y la búsqueda solo compara vectores del mismo modelo: cambiar de modelo no mezcla resultados.
- **Incremental:** si cambia el texto de una ficha (por ejemplo, porque la normalización o una revisión cambió su categoría), solo esa ficha se vuelve a codificar.
- **PyTorch solo para CPU** (índice `download.pytorch.org/whl/cpu`) en el PC y en Streamlit: la versión con CUDA pesa más de 2 GB y no hace falta para 77 fichas.

Pruebas: 119 en verde con un codificador falso (sin descargar el modelo) y la prueba de aceptación con el modelo real (`EVALUAR_EMBEDDINGS=1 uv run --group embed pytest tests/test_busqueda.py`), también en verde.

## 3. Pasos en tu PC

Después de cargar y normalizar en Supabase (`docs/sprint2.md` §3):

```powershell
git pull
uv sync --group embed          # instala sentence-transformers y PyTorch (CPU)
uv run --group embed python -m pipeline.embed generar
uv run --group embed python -m pipeline.embed evaluar
```

La primera vez descarga el modelo (~470 MB). `evaluar` imprime la tabla de aciertos sobre los datos de Supabase.

## 4. Streamlit Cloud

`app/requirements.txt` ya incluye `torch` (CPU) y `sentence-transformers`. Al desplegar (pasos en `docs/sprint3.md` §3.2), agrega a los *Secrets*:

```toml
EMBEDDING_MODELO = "intfloat/multilingual-e5-small"
```

La primera búsqueda tarda unos segundos mientras se descarga y carga el modelo; luego queda en memoria para todas las visitas. **Riesgo:** la app con el modelo usa ~1 GB en local; si Streamlit Cloud la reinicia por memoria, la alternativa es cambiar a una librería más liviana basada en ONNX (sin PyTorch) manteniendo el mismo modelo. Eso cambiaría una decisión del diseño, así que se propondría antes de hacerlo.
