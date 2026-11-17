# Sprint 2 — Normalización

17 de noviembre de 2026 · **Estado: código listo y probado; falta la corrida con gemma2:2b y la revisión humana de la muestra.**

## Criterios de aceptación

| Criterio | Estado |
|---|---|
| Tres campos normalizados sin costo externo | ✅ Código listo (objeto, material, estado de conservación; técnica también). Reglas probadas sobre las 77 fichas reales; el LLM local se corre en tu PC (§3) |
| Muestra de 50 por campo revisada | ⏳ Requiere una persona: `muestra` genera el CSV; falta completar `valor_correcto` |
| Aciertos por método documentados | ⏳ `metricas` los calcula a partir de la muestra revisada |
| Umbral calibrado | ⏳ `metricas` propone el umbral; se registra aquí y en `.env` |

## 1. Qué se construyó

| Pieza | Qué hace |
|---|---|
| `vocab/categorias.csv`, `vocab/terminos.csv` | Vocabulario **provisorio**: categorías por campo y los 34 términos AAT / Tesauro Regional presentes en Magallanes con su categoría (ver `vocab/LEEME.md`) |
| `pipeline/normalize/reglas.py` | Reglas antes que IA: ID de término → sinónimo. En material, detecta conflictos con la descripción |
| `pipeline/normalize/llm.py` | Interfaz `Normalizador` y `NormalizadorOllama` (modelo por `LLM_MODELO`): JSON con esquema, solo puede elegir una categoría del vocabulario o "otro" |
| `prompts/normalizar_v1.md` | Prompt versionado (`version_prompt = v1`) |
| `pipeline/normalize/proceso.py` | Normaliza lo pendiente y guarda método, confianza, modelo, versión, origen, entrada y hash de la ficha |
| `pipeline/normalize/calidad.py` | Muestra para revisión, aciertos por método y calibración del umbral |
| `db/migrations/005_…sql` | `normalizaciones.origen`, `.entrada` y `.hash_ficha` (aplicada también en Supabase) |

Comportamiento:

- **Unidad:** cada valor de cada campo por separado (`surdoc_id`, `campo`, `orden`). Si la ficha no declara objeto o material, se infiere de la descripción con `origen = descripcion`.
- **Reglas:** ID conocido → confianza 0,99; sinónimo → 0,95. Si la descripción no menciona ninguno de los materiales declarados pero sí otro, la confianza baja a 0,5 para forzar revisión.
- **LLM:** temperatura 0, salida validada con Pydantic. Si responde algo inválido, se reintenta una vez; si vuelve a fallar se guarda "otro" con confianza 0 (va a revisión). Si Ollama no está disponible, la corrida se detiene y lo avanzado queda guardado.
- **Incremental:** pendiente = sin normalización para esta versión de prompt, o normalizada sobre otra versión de la ficha (el hash guardado no coincide con el actual).
- **Versiones:** un prompt nuevo (`prompts/normalizar_v2.md`, `--version v2`) agrega filas sin borrar las de v1. `revisiones` nunca se toca.
- **Tiempo:** cada corrida queda en `ejecuciones` con duración total, número de llamadas al LLM y mediana por llamada.

## 2. Resultado de las reglas sobre las 77 fichas reales

Corrida `--sin-llm` en la base local:

| Campo | Valores | Por ID | Por sinónimo | Requieren LLM |
|---|---|---|---|---|
| Objeto | 77 | 62 | 2 | 12 términos ambiguos + 1 desde la descripción (`16-972`) |
| Material | 79 | 38 | 0 | 41 desde la descripción |
| Técnica | 3 | 2 | 1 | 0 |
| Estado de conservación | 77 | 0 | 77 | 0 |
| **Total** | **236** | **102** | **80** | **54** |

Las reglas resuelven 182 de 236 valores (77 %) sin IA. Los 54 restantes son los esperados: 41 materiales que solo están en la descripción, 12 objetos con términos ambiguos dejados a propósito sin regla y 1 ficha sin objeto (Guaica, Disco arqueológico, "Piedra" como objeto, Lito geométrico, Piedra perforada, Instrumento, Lana).

Conflictos detectados por las reglas (confianza 0,5 → revisión): `16-872` (material "Madera", descripción de fragmento cerámico) y `16-494` (flecha declarada de madera; la descripción solo menciona la punta de piedra). Una primera versión marcaba también `16-919` (declara Piedra y Cuero; la descripción habla de cuero): se corrigió para comparar contra todos los materiales declarados en la ficha.

## 3. Pasos en tu PC

En PowerShell, dentro de `Documents\Proyecto-IA-Museos`:

```powershell
git pull
uv sync
```

Edita `.env` (cópialo de `.env.example` si no existe):

- `DATABASE_URL`: cadena de Supabase en Settings → Database → Connection string → **Session pooler** (funciona con IPv4). Reemplaza `[YOUR-PASSWORD]`; si la contraseña tiene símbolos como `@` o `#`, codifícalos (`%40`, `%23`).
- `LLM_MODELO=gemma2:2b`
- `SURDOC_USER_AGENT`: deja el del ejemplo o pon un correo de contacto del proyecto.

```powershell
# 1. Cargar las 77 fichas en Supabase (~3 min)
uv run python -m pipeline.run --museo 16

# 2. Normalizar con reglas + gemma2:2b (Ollama abierto)
uv run python -m pipeline.normalize correr

# 3. Exportar las muestras para revisión
uv run python -m pipeline.normalize muestra --campo material
uv run python -m pipeline.normalize muestra --campo objeto
```

Pégame el resumen que imprime el paso 2 (la línea "Listo …").

**Revisión humana (idealmente con la arqueóloga):** abre `revision/muestra_material_v1.csv` y `revision/muestra_objeto_v1.csv` en Excel. Para cada fila, escribe en `valor_correcto` la categoría correcta (de `vocab/categorias.csv`) aunque coincida con la propuesta; usa `comentario` para dudas. Guarda como CSV UTF-8. Luego:

```powershell
uv run python -m pipeline.normalize metricas revision/muestra_material_v1.csv revision/muestra_objeto_v1.csv
```

Eso imprime los aciertos por método y el umbral recomendado. Con eso se cierran los criterios pendientes y se publica la métrica.

Estado de conservación y técnica no necesitan muestra: los 77 estados vienen de un vocabulario cerrado (3 valores) y las 3 técnicas se pueden revisar todas a mano.

## 4. Decisiones abiertas

- **Categorías provisorias:** las de material y tipo de objeto deben validarse con la arqueóloga (ver `vocab/LEEME.md`). Cambiarlas implica una nueva versión de prompt.
- **Umbral:** se parte en 0,8 hasta tener la muestra revisada.
- **Método `llm` desde la descripción:** se registra con `origen = descripcion`. Si la revisión muestra que esos valores aciertan mucho menos, conviene mandarlos siempre a revisión en la primera ronda.
