# Sprint 3 — Dashboard y revisión (MVP)

17 de noviembre de 2026 · **Estado: app lista y probada en local; falta desplegarla en Streamlit Community Cloud (requiere tu cuenta).**

## Criterios de aceptación

| Criterio | Estado |
|---|---|
| URL pública funcionando | ⏳ App lista; el despliegue se hace con tu cuenta (§3) |
| Sin sesión no se puede escribir | ✅ Probado: `anon` no puede insertar en `revisiones`; un usuario autenticado que no está en `revisores` tampoco; la app no tiene ninguna clave con permisos de escritura |
| Una corrección del revisor sobrevive a una nueva versión de prompt | ✅ Probado (`tests/test_app.py::test_revision_firma_con_el_usuario_y_sobrevive_a_un_prompt_nuevo`) |

Verificación: 112 pruebas en verde; la app se recorrió en un navegador contra la base local (panel, filtros, detalle de ficha, inicio de sesión rechazado para una usuaria no autorizada, revisión guardada y reflejada como "revisado").

## 1. Qué se construyó

**Base de datos** (`db/migrations/006_valor_vigente.sql`, aplicada en Supabase):

| Objeto | Para qué |
|---|---|
| `valor_vigente` (vista) | Valor final de cada campo: la revisión humana más reciente gana siempre; si no hay, la normalización más reciente. Estado: `revisado`, `propuesto` o `en_revision` (confianza bajo el umbral, "otro" o conflicto) |
| `fichas_publicas` (vista) | Columnas publicables de cada ficha vigente (sin nombre de sitio) y su URL en SURDOC |
| `cola_revision` (vista) | Valores en revisión con el contexto de la ficha |
| `categorias` (tabla) | Categorías válidas por campo, copiadas de `vocab/categorias.csv` en cada corrida de normalización. Una revisión con una categoría inexistente es rechazada por la base (clave foránea) |
| `parametros` (tabla) | `umbral_confianza` (0,8 hasta calibrarlo en el Sprint 2) |

Las vistas usan `security_invoker`: respetan el RLS de quien consulta. `revisiones.revisado_por` toma `auth.uid()` por defecto, así que la firma la pone la base, no la app.

**App** (`app/`, Streamlit):

| Página | Contenido |
|---|---|
| Colección (pública) | Indicadores, filtros (texto, tipo, material, conservación, colección, validación), gráficos de material, tipo y conservación coloreados por validación, tabla con enlace a SURDOC y detalle de ficha con la trazabilidad de cada valor (original, método, modelo, prompt, confianza, justificación) y la fotografía cargada desde SURDOC con su crédito |
| Revisión (con sesión) | Inicio de sesión con Supabase Auth; cola paginada con descripción, valor declarado, propuesta, método y justificación; se guarda la categoría correcta con un clic |
| Método y fuentes (pública) | Cómo se extrae y normaliza, qué no se normaliza, protección del patrimonio, valores por método y umbral vigente |

`app/datos.py` separa el acceso a datos: en producción `FuenteSupabase` usa la API REST con la clave pública (anon) y, para revisar, el token de la sesión de la revisora; en desarrollo `FuentePostgres` usa el Postgres local cambiando a los roles `anon`/`authenticated`, de modo que las pruebas ejercitan el mismo RLS.

## 2. Ejecutar en local

```bash
docker compose up -d
uv sync
# (opcional) revisora de prueba para la página de revisión:
#   insert into revisores (usuario_id, nombre) values ('<uuid>', 'Revisora de prueba');
DATABASE_URL=postgresql://observatorio:observatorio@localhost:5432/observatorio \
REVISOR_LOCAL_CORREO=revisora@ejemplo.cl REVISOR_LOCAL_ID=<uuid> \
uv run streamlit run app/app.py
```

## 3. Despliegue (tu cuenta)

### 3.1 Supabase: datos y revisora

1. Carga y normaliza los datos en Supabase desde tu PC (`docs/sprint2.md` §3). Sin eso la app mostrará "Todavía no hay fichas cargadas".
2. **Authentication → Sign In / Providers → Email:** deja activo el inicio con correo y **desactiva "Allow new users to sign up"**. Solo las cuentas que tú crees podrán entrar.
3. **Authentication → Users → Add user → Create new user:** correo y contraseña de la revisora, con *Auto Confirm User*.
4. **SQL Editor:** autoriza a esa cuenta como revisora:
   ```sql
   insert into revisores (usuario_id, nombre)
   select id, 'Nombre de la revisora' from auth.users where email = 'correo@de.la.revisora';
   ```
5. **SQL Editor:** quita los permisos por defecto en los objetos nuevos (capa extra de defensa; RLS ya bloquea la escritura):
   ```sql
   revoke insert, update, delete, truncate on categorias, parametros, valor_vigente,
       fichas_publicas, cola_revision from anon, authenticated;
   ```

### 3.2 Streamlit Community Cloud

1. Entra en <https://share.streamlit.io> con tu cuenta de GitHub y autoriza el acceso al repositorio (si es privado, Streamlit lo pide explícitamente).
2. **Create app → Deploy a public app from GitHub:**
   - Repository: `maracenam/Proyecto-IA-Museos`
   - Branch: `claude/cool-bell-p9p0n3` (o `main` cuando exista)
   - Main file path: `app/app.py`
   - App URL: por ejemplo `observatorio-surdoc`
3. **Advanced settings:** Python 3.12 y, en *Secrets*:
   ```toml
   SUPABASE_URL = "https://bksdjmwdvrxwtlniatbm.supabase.co"
   SUPABASE_ANON_KEY = "<clave publishable/anon de Settings → API Keys>"
   ```
   **Nunca pongas `DATABASE_URL` ni la clave `service_role` en Streamlit:** la app pública solo debe tener la clave anónima.
4. **Deploy.** Las dependencias salen de `app/requirements.txt`.

Comprobación final (criterios del sprint): abrir la URL sin sesión y ver las fichas; entrar a "Revisión" con un correo no autorizado (debe rechazar); entrar con la revisora y guardar una corrección (debe verse como "Revisado por persona" en la Colección).

## 4. Pendiente y decisiones

- **Búsqueda en lenguaje natural:** es del Sprint 4; por ahora la Colección tiene búsqueda por texto y filtros.
- **Valores "Sin normalizar":** hasta correr gemma2:2b (Sprint 2), los 41 materiales y 13 objetos que requieren IA aparecen como "Sin normalizar". Es honesto y se completa solo al correr la normalización.
- **Texto libre con sitios:** la vista pública no incluye "Historia del objeto" ni "Historia de propiedad y uso", que pueden nombrar sitios (`16-872`). Se mantienen fuera hasta revisarlos con la arqueóloga.
