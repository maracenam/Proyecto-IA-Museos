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

## 6. Revisar la muestra de calidad (en la app, sin comandos)

La muestra ya está creada en Supabase: 50 valores de material y 50 de objeto elegidos al azar. Se revisa en la app, página **Revisión → Muestra de calidad**, con la cuenta de revisora (ver "Fuera del PC"):

- Para cada valor ves la ficha, la foto y lo que propone el sistema.
- **Correcto** si está bien (un clic), o elige la categoría correcta y **Guardar corrección**.
- **Saltar** deja un valor para después; el avance queda guardado y se puede seguir otro día.

Son unos 20–30 minutos, idealmente con la arqueóloga. La precisión por método se publica sola en **Método y fuentes**. Si quieres verla también en la terminal:

```powershell
uv run python -m pipeline.normalize metricas
```

Si en el futuro se normaliza con un prompt nuevo, la muestra de esa versión se crea con `uv run python -m pipeline.normalize muestra --campo material --version v2` (y `--campo objeto`).

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

## 9. Compartir la app desde tu PC con un enlace público

Sirve para mostrarla a alguien sin desplegarla en la web. Usa un túnel gratuito de Cloudflare: no necesita cuenta ni abrir puertos del router.

Una vez:

```powershell
winget install --id Cloudflare.cloudflared
```

(Cierra y abre PowerShell después de instalar.) En `.env` deben estar `SUPABASE_URL` y `SUPABASE_ANON_KEY` (la clave **pública**, nunca la `service_role`).

Cada vez que quieras compartirla:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\publicar_desde_pc.ps1
```

El script inicia la app, abre el túnel, muestra un enlace `https://….trycloudflare.com`, lo copia al portapapeles y lo abre en tu navegador. Mándalo por correo o WhatsApp.

- Funciona **mientras la ventana siga abierta y el PC encendido**. Para cortar: `Ctrl+C` o cerrar la ventana.
- El enlace **cambia cada vez** que ejecutas el script.
- Quien lo abra solo puede **mirar y buscar**. La página Revisión pide correo y contraseña de una cuenta autorizada.
- La app publicada solo recibe la clave pública: la cadena de conexión de la base (`DATABASE_URL`) nunca sale de tu PC.
- Si algo falla, el mensaje indica qué revisar; los registros quedan en `logs\app_errores.log` y `logs\tunel.log`.

Para un enlace fijo que no dependa del PC, despliega en Streamlit Cloud (tabla de abajo).

---

## Fuera del PC (en la web)

| Dónde | Qué | Detalle |
|---|---|---|
| Supabase → Authentication | Desactivar registros públicos, crear la cuenta de la revisora y autorizarla con SQL | `docs/sprint3.md` §3.1 |
| Supabase → SQL Editor | Quitar permisos por defecto en las vistas y funciones nuevas (`revoke …`) | `docs/sprint3.md` §3.1, paso 5 |
| GitHub → Settings → Secrets and variables → Actions | Secret `SUPABASE_DATABASE_URL` (la misma cadena del paso 2) y variable `SURDOC_USER_AGENT`; correr el workflow *extraccion* a mano; activar correos de workflows fallidos | `docs/sprint5.md` §2 |
| share.streamlit.io | Desplegar `app/app.py` con los secrets `SUPABASE_URL`, `SUPABASE_ANON_KEY` y `EMBEDDING_MODELO` | `docs/sprint3.md` §3.2 y `docs/sprint4.md` §4 |
