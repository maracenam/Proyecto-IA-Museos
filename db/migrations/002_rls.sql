-- 002_rls.sql
-- Seguridad a nivel de fila (RLS).
--   * Lectura pública (anon y authenticated) de las capas plata, oro y referencia.
--   * Bronce (registros_raw, cuarentena) es privado: puede contener datos no publicables
--     (ej. nombre de sitio arqueológico) y HTML de depuración.
--   * Solo un revisor registrado en `revisores` puede insertar revisiones, firmadas con su uid.
--   * El pipeline escribe con la conexión del dueño de las tablas (o service_role en Supabase),
--     que no está sujeta a estas políticas. Nunca se usa esa clave en la app pública.
-- Idempotente.

-- En local no existen los roles ni auth.uid() de Supabase: se crean solo si faltan.
do $$
begin
    if not exists (select 1 from pg_roles where rolname = 'anon') then
        create role anon nologin;
    end if;
    if not exists (select 1 from pg_roles where rolname = 'authenticated') then
        create role authenticated nologin;
    end if;
end
$$;

create schema if not exists auth;

do $$
begin
    if not exists (
        select 1 from pg_proc p join pg_namespace n on n.oid = p.pronamespace
        where n.nspname = 'auth' and p.proname = 'uid'
    ) then
        -- Equivalente local de auth.uid() de Supabase (lee el claim 'sub' del JWT).
        execute $f$
            create function auth.uid() returns uuid language sql stable as
            'select nullif(current_setting(''request.jwt.claim.sub'', true), '''')::uuid'
        $f$;
    end if;
end
$$;

grant usage on schema auth to anon, authenticated;
grant usage on schema public to anon, authenticated;

-- Activar RLS en todas las tablas.
alter table museos             enable row level security;
alter table registros_raw      enable row level security;
alter table cuarentena         enable row level security;
alter table registros          enable row level security;
alter table registro_terminos  enable row level security;
alter table vocabulario        enable row level security;
alter table normalizaciones    enable row level security;
alter table revisores          enable row level security;
alter table revisiones         enable row level security;
alter table embeddings         enable row level security;
alter table ejecuciones        enable row level security;

-- Bronce: sin acceso para anon/authenticated (Supabase otorga permisos por defecto; se revocan).
revoke all on registros_raw, cuarentena from anon, authenticated;

-- Revisores: nadie fuera del dueño ve la lista completa.
revoke all on revisores from anon, authenticated;

-- Lectura pública.
grant select on museos, registros, registro_terminos, vocabulario,
                normalizaciones, revisiones, embeddings, ejecuciones
    to anon, authenticated;

-- Nadie de la app pública escribe, salvo inserciones en revisiones.
revoke insert, update, delete, truncate on museos, registros, registro_terminos, vocabulario,
                normalizaciones, revisiones, embeddings, ejecuciones
    from anon, authenticated;
grant insert on revisiones to authenticated;
grant usage on sequence revisiones_id_seq to authenticated;

do $$
declare
    t text;
begin
    foreach t in array array['museos', 'registros', 'registro_terminos', 'vocabulario',
                             'normalizaciones', 'revisiones', 'embeddings', 'ejecuciones']
    loop
        execute format('drop policy if exists lectura_publica on %I', t);
        execute format('create policy lectura_publica on %I for select to anon, authenticated using (true)', t);
    end loop;
end
$$;

-- Un revisor puede comprobar su propia fila en `revisores` (necesario para la política de abajo).
grant select on revisores to authenticated;
drop policy if exists revisor_se_ve_a_si_mismo on revisores;
create policy revisor_se_ve_a_si_mismo on revisores
    for select to authenticated
    using (usuario_id = auth.uid());

drop policy if exists revisor_inserta on revisiones;
create policy revisor_inserta on revisiones
    for insert to authenticated
    with check (
        revisado_por = auth.uid()
        and exists (select 1 from revisores r where r.usuario_id = auth.uid())
    );
