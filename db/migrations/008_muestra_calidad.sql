-- 008_muestra_calidad.sql
-- Muestra de calidad (Sprint 2, criterio "muestra de 50 por campo revisada"), revisada desde la
-- app en vez de CSV:
--   * muestra_calidad: valores normalizados elegidos al azar (orden reproducible) y la respuesta
--     de una revisora. Lectura pública: la precisión publicada se puede auditar.
--   * responder_muestra(): guarda la respuesta y, a la vez, una fila en `revisiones`, de modo que
--     el valor queda validado por una persona en valor_vigente. Corre como quien llama
--     (security invoker): RLS y la verificación de `revisores` aplican igual que en revisiones.
--   * muestra_calidad_detalle: lo que necesita la tarjeta de revisión (contexto de la ficha).
-- Idempotente.

create table if not exists muestra_calidad (
    surdoc_id       text not null,
    campo           text not null,
    orden           integer not null,
    version_prompt  text not null,
    posicion        integer not null,           -- orden de presentación (al azar, reproducible)
    valor_propuesto text not null,
    metodo          text not null,
    confianza       numeric(4, 3) not null,
    valor_correcto  text,                       -- null = pendiente
    revisado_por    uuid,
    fecha_revision  timestamptz,
    creada_en       timestamptz not null default now(),
    primary key (surdoc_id, campo, orden, version_prompt),
    foreign key (surdoc_id, campo, orden, version_prompt)
        references normalizaciones (surdoc_id, campo, orden, version_prompt) on delete cascade,
    foreign key (campo, valor_correcto) references categorias (campo, categoria)
);

create index if not exists muestra_calidad_campo_idx on muestra_calidad (campo, posicion);

comment on table muestra_calidad is
    'Muestra aleatoria de valores normalizados revisada por una persona: fuente de la precisión publicada.';

alter table muestra_calidad enable row level security;

drop policy if exists lectura_publica on muestra_calidad;
create policy lectura_publica on muestra_calidad for select to anon, authenticated using (true);

drop policy if exists revisor_responde on muestra_calidad;
create policy revisor_responde on muestra_calidad
    for update to authenticated
    using (exists (select 1 from revisores r where r.usuario_id = (select auth.uid())))
    with check (
        revisado_por = (select auth.uid())
        and exists (select 1 from revisores r where r.usuario_id = (select auth.uid()))
    );

grant select on muestra_calidad to anon, authenticated;
revoke insert, update, delete, truncate on muestra_calidad from anon, authenticated;
grant update (valor_correcto, revisado_por, fecha_revision) on muestra_calidad to authenticated;

create or replace function responder_muestra(
    p_surdoc_id text,
    p_campo text,
    p_orden integer,
    p_version_prompt text,
    p_valor_correcto text
)
returns void
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_propuesto text;
begin
    if not exists (select 1 from public.revisores r where r.usuario_id = (select auth.uid())) then
        raise exception 'Tu usuario no está autorizado como revisor' using errcode = '42501';
    end if;

    update public.muestra_calidad
       set valor_correcto = p_valor_correcto,
           revisado_por = (select auth.uid()),
           fecha_revision = now()
     where surdoc_id = p_surdoc_id and campo = p_campo and orden = p_orden
       and version_prompt = p_version_prompt
    returning valor_propuesto into v_propuesto;

    if not found then
        raise exception 'Ese valor no está en la muestra' using errcode = 'P0002';
    end if;

    -- Toda decisión humana queda también como revisión: el valor pasa a "revisado por persona".
    insert into public.revisiones (surdoc_id, campo, orden, valor_anterior, valor_corregido)
    values (p_surdoc_id, p_campo, p_orden, v_propuesto, p_valor_correcto);
end
$$;

revoke execute on function responder_muestra(text, text, integer, text, text) from public, anon;
grant execute on function responder_muestra(text, text, integer, text, text) to authenticated;

create or replace view muestra_calidad_detalle with (security_invoker = true) as
select
    m.surdoc_id, m.campo, m.orden, m.version_prompt, m.posicion, m.valor_propuesto, m.metodo,
    m.confianza, m.valor_correcto, m.fecha_revision,
    n.origen, n.entrada, n.justificacion, n.modelo,
    f.objeto, f.tecnica_material, f.descripcion, f.url_ficha, f.url_imagen, f.credito_imagen
from muestra_calidad m
join normalizaciones n using (surdoc_id, campo, orden, version_prompt)
join fichas_publicas f using (surdoc_id);

grant select on muestra_calidad_detalle to anon, authenticated;
revoke insert, update, delete, truncate on muestra_calidad_detalle from anon, authenticated;
