# Pasos en el PC (Windows)

Todo lo que hay que correr en el PC para dejar el observatorio funcionando con datos reales en Supabase. Se hace una sola vez; después la extracción corre sola en GitHub y el procesamiento con el Programador de tareas.

Todos los comandos van en **PowerShell**, dentro de la carpeta del proyecto.

## 0. Requisitos (una vez)

Ya instalados en la sesión anterior: Git, uv y Ollama con `gemma2:2b`. Si falta alguno:

```powershell
winget install Git.Git
winget install astral-sh.uv
winget install Ollama.Ollama
ollama pull gemma2:2b
```

## 1. Actualizar el proyecto

```powershell
cd $HOME\Documents\Proyecto-IA-Museos
git pull
uv sync --group embed
```

`uv sync --group embed` instala también sentence-transformers y PyTorch para CPU (unos minutos la primera vez).

## 2. Configurar `.env`

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
notepad .env
```

Cambia solo esta línea:

```
DATABASE_URL=postgresql://postgres.bksdjmwdvrxwtlniatbm:TU_CONTRASEÑA@aws-0-sa-east-1.pooler.supabase.com:5432/postgres
```

Copia la cadena exacta desde Supabase → proyecto `observatorio-surdoc` → botón **Connect** → **Session pooler** (el host puede variar; usa el que muestra Supabase). Reemplaza `[YOUR-PASSWORD]` por la contraseña de la base. Si la contraseña tiene símbolos, codifícalos: `@` → `%40`, `#` → `%23`, `/` → `%2F`, `:` → `%3A`. Si no la recuerdas: Settings → Database → *Reset database password*.

`LLM_MODELO=gemma2:2b` y `EMBEDDING_MODELO=intfloat/multilingual-e5-small` ya vienen en el ejemplo. `.env` nunca se sube al repositorio.

## 3. Cargar las fichas en Supabase (~3 min)

```powershell
uv run python -m pipeline.run --museo 16
```

Esperado: `77 listadas (SURDOC informa 77), 77 nuevas o cambiadas, 0 sin cambios, 0 en cuarentena`.

## 4. Normalizar con reglas + gemma2:2b (~1–2 min)

Con Ollama abierto:

```powershell
uv run python -m pipeline.normalize correr
```

Esperado: `236 pendientes, 236 guardados {...'llm': 54...}`. **Pega la línea "Listo …" en el chat.**

## 5. Generar los embeddings para la búsqueda (~1 min)

```powershell
uv run --group embed python -m pipeline.embed generar
uv run --group embed python -m pipeline.embed evaluar
```

La primera vez descarga el modelo (~470 MB). `evaluar` imprime la tabla de las 10 consultas de prueba. **Pega la última línea en el chat** (debe decir 10/10).

## 6. Exportar la muestra para revisión humana

```powershell
uv run python -m pipeline.normalize muestra --campo material
uv run python -m pipeline.normalize muestra --campo objeto
```

Crea `revision\muestra_material_v1.csv` y `revision\muestra_objeto_v1.csv`. Ábrelos en Excel (idealmente con la arqueóloga) y llena la columna **valor_correcto** en cada fila con la categoría correcta, aunque coincida con la propuesta (categorías en `vocab\categorias.csv`). Guarda como **CSV UTF-8**. Luego:

```powershell
uv run python -m pipeline.normalize metricas revision\muestra_material_v1.csv revision\muestra_objeto_v1.csv
```

**Pega el resultado en el chat**: con eso se publica la precisión por método y se fija el umbral.

## 7. Programar el procesamiento diario

```powershell
powershell -ExecutionPolicy Bypass -File scripts\procesar_pendientes.ps1
Get-Content (Get-ChildItem logs\procesar_*.log | Sort-Object Name | Select-Object -Last 1)
powershell -ExecutionPolicy Bypass -File scripts\registrar_tarea_windows.ps1
```

La primera línea lo prueba a mano (debe terminar en `== Listo`, con 0 pendientes porque ya procesaste todo); la segunda muestra el registro; la tercera lo programa todos los días a las 20:00 (`-Hora 21:30` para cambiarla). Si algo falla, pega el registro en el chat.

## 8. (Opcional) Ver la app en tu PC con los datos de Supabase

```powershell
$env:SUPABASE_URL = "https://bksdjmwdvrxwtlniatbm.supabase.co"
$env:SUPABASE_ANON_KEY = "<clave publishable/anon de Supabase → Settings → API Keys>"
uv run --group embed streamlit run app/app.py
```

Se abre en <http://localhost:8501>. Es la misma configuración que tendrá Streamlit Cloud.

---

## Fuera del PC (en la web)

| Dónde | Qué | Detalle |
|---|---|---|
| Supabase → Authentication | Desactivar registros públicos, crear la cuenta de la revisora y autorizarla con SQL | `docs/sprint3.md` §3.1 |
| Supabase → SQL Editor | Quitar permisos por defecto en las vistas nuevas (`revoke …`) | `docs/sprint3.md` §3.1, paso 5 |
| GitHub → Settings → Secrets and variables → Actions | Secret `SUPABASE_DATABASE_URL` (la misma cadena del paso 2) y variable `SURDOC_USER_AGENT`; correr el workflow *extraccion* a mano; activar correos de workflows fallidos | `docs/sprint5.md` §2 |
| share.streamlit.io | Desplegar `app/app.py` con los secrets `SUPABASE_URL`, `SUPABASE_ANON_KEY` y `EMBEDDING_MODELO` | `docs/sprint3.md` §3.2 y `docs/sprint4.md` §4 |
