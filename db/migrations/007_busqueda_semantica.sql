-- 007_busqueda_semantica.sql
-- Sprint 4: búsqueda en lenguaje natural con pgvector.
--   * embeddings.hash_texto: permite regenerar solo los embeddings cuyo texto cambió.
--   * buscar_fichas(): devuelve las fichas públicas más parecidas a un vector de consulta.
--     Corre con los permisos de quien llama (security invoker): la app pública la usa con la
--     clave anon y solo ve fichas de `fichas_publicas`.
-- Idempotente.

alter table embeddings add column if not exists hash_texto text;

-- El tipo vector vive en el esquema extensions (migración 003). Supabase ya da este permiso a
-- anon y authenticated; en Postgres local hay que darlo para que puedan usar buscar_fichas.
grant usage on schema extensions to anon, authenticated;

comment on column embeddings.texto is
    'Texto con el que se generó el vector. Solo usa campos públicos (fichas_publicas y valor_vigente).';

create or replace function buscar_fichas(
    consulta extensions.vector,
    modelo_busqueda text,
    limite integer default 10
)
returns table (surdoc_id text, similitud double precision)
language sql
stable
security invoker
set search_path = public, extensions
as $$
    select e.surdoc_id, 1 - (e.vector <=> consulta) as similitud
    from embeddings e
    join fichas_publicas f on f.surdoc_id = e.surdoc_id
    where e.modelo = modelo_busqueda
      and vector_dims(e.vector) = vector_dims(consulta)
    order by e.vector <=> consulta
    limit least(greatest(coalesce(limite, 10), 1), 50)
$$;

comment on function buscar_fichas is
    'Fichas públicas más parecidas al vector de consulta (distancia coseno), para el modelo indicado.';

revoke execute on function buscar_fichas(extensions.vector, text, integer) from public;
grant execute on function buscar_fichas(extensions.vector, text, integer) to anon, authenticated;
