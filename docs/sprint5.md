# Sprint 5 — Escala y portafolio

18 de noviembre de 2026 · **Estado: automatización y README listos; los museos adicionales quedan pendientes por decisión del usuario.**

## Criterios de aceptación

| Criterio | Estado |
|---|---|
| Dos o tres museos regionales más | ⏸️ Pendiente por decisión. El pipeline ya extrae todos los museos de la tabla `museos`: sumar uno es agregar una fila |
| Extracción cada 3 días en GitHub Actions con aviso de fallas | ✅ Listo (`.github/workflows/extraccion.yml`); falta cargar el secret y probarlo en GitHub (§2) |
| Normalización local programada | ✅ Scripts listos (`scripts/`); falta registrarla en tu PC (§3). No se pudieron probar aquí (no hay PowerShell en este entorno) |
| README listo para mostrar a consultoras | ✅ Con arquitectura, resultados medidos y captura del panel |

Pruebas: 125 en verde. La extracción de todos los museos se corrió contra SURDOC real: 77 fichas sin cambios, código de salida 0 y resumen en Markdown.

## 1. Qué se construyó

**`python -m pipeline.run --todos`** extrae cada museo de la tabla `museos`. Un museo que falla no detiene a los demás. Códigos de salida:

| Código | Significado | Efecto en GitHub Actions |
|---|---|---|
| 0 | Todo bien | — |
| 1 | La extracción de algún museo se detuvo (ej. no se pudo leer el listado) | Corrida fallida → correo |
| 2 | Más del 20 % de las fichas en cuarentena: probablemente SURDOC cambió su HTML | Corrida fallida → correo |

El código 2 cubre el riesgo principal del proyecto: si SURDOC cambia su HTML, las fichas no se pierden (van a cuarentena con el HTML guardado), pero la corrida falla para que alguien lo note.

En GitHub Actions la corrida escribe un resumen en la página del run (`GITHUB_STEP_SUMMARY`), con listadas, nuevas, sin cambios, cuarentena y bajas por museo.

**`.github/workflows/extraccion.yml`**: cada 3 días a las 09:37 UTC (días 1, 4, 7… de cada mes; nunca pasan más de 3 días, bajo el límite de 7 días de inactividad de Supabase) y a mano desde la pestaña Actions, con opción de un solo museo. El código del museo se pasa por variable de entorno y se valida, para evitar inyección de comandos.

**`scripts/procesar_pendientes.ps1`** corre la normalización y los embeddings pendientes y guarda un registro en `logs/` (conserva los últimos 30). **`scripts/registrar_tarea_windows.ps1`** lo programa a diario en el Programador de tareas; si el PC estaba apagado a esa hora, se ejecuta al encenderlo.

## 2. Activar la extracción en GitHub (tu cuenta)

1. **Secret con la conexión a Supabase:** GitHub → repositorio → Settings → Secrets and variables → Actions → *New repository secret*:
   - Nombre: `SUPABASE_DATABASE_URL`
   - Valor: la cadena de Supabase (Settings → Database → Connection string → **Session pooler**), con la contraseña.
2. **Variable con el User-Agent:** en la misma página, pestaña *Variables* → *New repository variable*:
   - Nombre: `SURDOC_USER_AGENT`
   - Valor: `ObservatorioSURDOC/0.1 (+https://github.com/maracenam/Proyecto-IA-Museos)` o con un correo de contacto.
3. **Probar:** Actions → *extraccion* → *Run workflow*. Debe terminar en verde con el resumen de Magallanes.
4. **Aviso por correo:** GitHub → tu foto → Settings → Notifications → *Actions*: marca **Email** y **Only notify for failed workflows**. GitHub envía el aviso a quien configuró el workflow programado.

Los workflows programados solo corren desde la rama por defecto del repositorio. Hoy es `claude/cool-bell-p9p0n3`; si se crea `main` y pasa a ser la rama por defecto, el workflow debe estar ahí.

## 3. Programar el procesamiento en tu PC

En PowerShell, dentro de `Documents\Proyecto-IA-Museos` (con `.env` configurado y Ollama instalado):

```powershell
git pull
uv sync --group embed
powershell -ExecutionPolicy Bypass -File scripts\procesar_pendientes.ps1      # prueba a mano
powershell -ExecutionPolicy Bypass -File scripts\registrar_tarea_windows.ps1  # diario a las 20:00
```

Revisa el resultado en `logs\procesar_*.log`. Para cambiar la hora: `-Hora 21:30`. Ollama debe estar abierto (se inicia solo con Windows si se instaló con el instalador oficial).

## 4. Pendiente

- **Museos adicionales:** cuando se decida, insertar cada museo en `museos` (código de institución en SURDOC, nombre, región, comuna) y correr el workflow a mano. Antes de sumarlo conviene revisar algunas fichas: otro museo puede usar etiquetas o vocabularios que el parser y `vocab/` aún no conocen (la cuarentena y el código 2 avisarán).
- **Etiquetas de versión** (`v0.1`…`v0.5`): pendientes de tu autorización para subirlas.
