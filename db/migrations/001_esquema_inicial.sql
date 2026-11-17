-- 001_esquema_inicial.sql
-- Tablas del "Modelo de datos" de DISENO_TECNICO.md, organizadas por capas.
-- Idempotente: se puede ejecutar más de una vez sin error ni duplicados.
-- Compatible con Postgres local (docker compose) y con Supabase.

-- pgvector en su propio esquema (recomendación de seguridad de Supabase).
create schema if not exists extensions;
create extension if not exists vector with schema extensions;

-- ---------------------------------------------------------------------------
-- Referencia
-- ---------------------------------------------------------------------------

create table if not exists museos (
    id                  serial primary key,
    nombre              text not null,
    codigo_institucion  integer not null unique,   -- código SURDOC (16 = Magallanes)
    region              text,
    comuna              text
);

comment on table museos is 'Instituciones de SURDOC incluidas en el observatorio.';

insert into museos (nombre, codigo_institucion, region, comuna)
values ('Museo Regional de Magallanes', 16, 'Magallanes y de la Antártica Chilena', 'Punta Arenas')
on conflict (codigo_institucion) do nothing;

-- ---------------------------------------------------------------------------
-- Bronce: lo extraído en bruto. Nunca se modifica el contenido parseado de
-- una versión; si cambia el hash, se reemplaza la fila y se reprocesa.
-- Capa privada: no se expone en la app pública.
-- ---------------------------------------------------------------------------

create table if not exists registros_raw (
    surdoc_id           text primary key,          -- ej. '16-447'
    url                 text not null,
    campos              jsonb not null,            -- campos parseados (incluye los no publicables, ej. nombre de sitio)
    hash_campos         text not null,             -- sha256 de los campos parseados en orden estable (nunca del HTML)
    fecha_extraccion    timestamptz not null default now(),
    fecha_ultima_vista  timestamptz not null default now()
);

create table if not exists cuarentena (
    surdoc_id   text not null,
    fecha       timestamptz not null default now(),
    url         text not null,
    error       text not null,
    html        text,                               -- HTML guardado solo para depurar
    primary key (surdoc_id, fecha)
);

-- ---------------------------------------------------------------------------
-- Plata: una fila por ficha, con los campos ya estructurados (valores originales).
-- ---------------------------------------------------------------------------

create table if not exists registros (
    surdoc_id               text primary key references registros_raw (surdoc_id),
    museo_id                integer not null references museos (id),
    titulo                  text,
    numero_inventario       text,
    clasificacion           text,
    coleccion               text,
    objeto                  text,
    descripcion             text,
    dimensiones             text,
    tecnica_material        text,                   -- texto original completo; el detalle va en registro_terminos
    procedencia             text,
    cultura_originaria      text,
    cultura_arqueologica    text,
    area_cultural           text,                   -- "primer nivel / segundo nivel"
    area_geografica         text,
    fecha_creacion          text,
    creador                 text,
    forma_ingreso           text,
    estado_conservacion     text,
    url_imagen              text,                   -- se carga desde SURDOC, nunca se republica
    credito_imagen          text,
    dado_de_baja            boolean not null default false,
    fecha_baja              timestamptz,
    actualizado_en          timestamptz not null default now()
);

create index if not exists registros_museo_idx on registros (museo_id);

-- Una fila por valor de un campo con vocabulario (un campo puede tener varios).
-- Para Técnica / Material, 'orden' es la posición del par técnica-material en la ficha,
-- de modo que tecnica#0 y material#0 forman el primer par.
create table if not exists registro_terminos (
    surdoc_id       text not null references registros (surdoc_id) on delete cascade,
    campo           text not null check (campo in ('objeto', 'nombre_alternativo', 'tecnica', 'material')),
    orden           integer not null check (orden >= 0),
    texto_original  text not null,
    fuente_termino  text check (fuente_termino in ('aat', 'tesauro_regional')),
    id_termino      text,                           -- ID en el AAT o en el Tesauro Regional, si la ficha lo enlaza
    primary key (surdoc_id, campo, orden),
    check ((fuente_termino is null) = (id_termino is null))
);

create index if not exists registro_terminos_termino_idx on registro_terminos (fuente_termino, id_termino);

-- ---------------------------------------------------------------------------
-- Referencia: vocabulario controlado del observatorio
-- ---------------------------------------------------------------------------

create table if not exists vocabulario (
    campo               text not null,
    fuente_termino      text not null check (fuente_termino in ('aat', 'tesauro_regional', 'observatorio')),
    id_termino          text not null,
    termino_preferido   text not null,
    sinonimos           text[] not null default '{}',
    termino_padre       text,
    categoria           text,                       -- categoría comparable: cerámica, lítico, óseo...
    primary key (campo, fuente_termino, id_termino)
);

-- ---------------------------------------------------------------------------
-- Oro: normalizaciones, revisiones humanas y embeddings
-- ---------------------------------------------------------------------------

create table if not exists normalizaciones (
    surdoc_id           text not null references registros (surdoc_id) on delete cascade,
    campo               text not null check (campo in ('objeto', 'tecnica', 'material', 'estado_conservacion')),
    orden               integer not null check (orden >= 0),
    version_prompt      text not null,              -- también para reglas (ej. 'reglas-v1')
    valor_normalizado   text not null,
    metodo              text not null check (metodo in ('regla_id', 'sinonimo', 'llm')),
    confianza           numeric(4, 3) not null check (confianza between 0 and 1),
    modelo              text,                       -- null si el método no usa LLM
    justificacion       text,
    fecha               timestamptz not null default now(),
    primary key (surdoc_id, campo, orden, version_prompt)
);

-- Personas autorizadas para escribir revisiones (usuarios de Supabase Auth).
create table if not exists revisores (
    usuario_id  uuid primary key,
    nombre      text not null,
    creado_en   timestamptz not null default now()
);

create table if not exists revisiones (
    id                  bigserial primary key,
    surdoc_id           text not null references registros (surdoc_id) on delete cascade,
    campo               text not null,
    orden               integer not null check (orden >= 0),
    valor_anterior      text,
    valor_corregido     text not null,
    revisado_por        uuid not null,
    fecha               timestamptz not null default now()
);

create index if not exists revisiones_valor_idx on revisiones (surdoc_id, campo, orden, fecha desc);

-- La dimensión del vector se fija en el Sprint 4, cuando se elija el modelo.
create table if not exists embeddings (
    surdoc_id   text not null references registros (surdoc_id) on delete cascade,
    modelo      text not null,
    vector      extensions.vector not null,
    texto       text not null,
    fecha       timestamptz not null default now(),
    primary key (surdoc_id, modelo)
);

-- ---------------------------------------------------------------------------
-- Auditoría
-- ---------------------------------------------------------------------------

create table if not exists ejecuciones (
    id                      bigserial primary key,
    tipo_proceso            text not null,          -- extraccion, normalizacion, embeddings
    inicio                  timestamptz not null default now(),
    fin                     timestamptz,
    registros_procesados    integer not null default 0,
    en_cuarentena           integer not null default 0,
    dados_de_baja           integer not null default 0,
    errores                 integer not null default 0,
    detalle                 jsonb,
    version_codigo          text
);
