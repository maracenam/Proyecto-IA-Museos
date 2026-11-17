-- 003_vector_en_extensions.sql
-- Mueve pgvector del esquema public a extensions en bases creadas con una versión
-- anterior de 001 (aviso "Extension in Public" de Supabase). Idempotente.

create schema if not exists extensions;

do $$
begin
    if exists (
        select 1 from pg_extension e join pg_namespace n on n.oid = e.extnamespace
        where e.extname = 'vector' and n.nspname = 'public'
    ) then
        alter extension vector set schema extensions;
    end if;
end
$$;
