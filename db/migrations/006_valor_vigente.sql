-- 006_valor_vigente.sql
-- Sprint 3: capa de consulta para la app pública y la cola de revisión.
--   * categorias: categorías válidas por campo (copia de vocab/categorias.csv).
--   * parametros: umbral de confianza para mandar valores a revisión.
--   * valor_vigente: la revisión humana más reciente gana siempre; si no hay, la normalización
--     más reciente (de cualquier versión de prompt). Así un prompt nuevo nunca borra una revisión.
--   * fichas_publicas y cola_revision: lo que lee la app.
-- Las vistas usan security_invoker para que respeten el RLS de quien consulta (sin eso, una
-- vista corre con los permisos de su dueño y se saltaría RLS). Idempotente.

create table if not exists categorias (
    campo       text not null,
    categoria   text not null,
    descripcion text,
    primary key (campo, categoria)
);

create table if not exists parametros (
    clave       text primary key,
    valor       text not null,
    descripcion text
);

insert into parametros (clave, valor, descripcion)
values ('umbral_confianza', '0.8',
        'Valores con confianza menor (o "otro") van a la cola de revisión. Se calibra con la muestra revisada.')
on conflict (clave) do nothing;

-- Una corrección solo puede ser una categoría existente del campo.
do $$
begin
    if not exists (select 1 from pg_constraint where conname = 'revisiones_categoria_valida') then
        alter table revisiones add constraint revisiones_categoria_valida
            foreign key (campo, valor_corregido) references categorias (campo, categoria);
    end if;
end
$$;

-- La revisión se firma sola con el usuario que inició sesión.
alter table revisiones alter column revisado_por set default auth.uid();

create or replace view valor_vigente with (security_invoker = true) as
with ultima_normalizacion as (
    select distinct on (surdoc_id, campo, orden) *
    from normalizaciones
    order by surdoc_id, campo, orden, fecha desc, version_prompt desc
),
ultima_revision as (
    select distinct on (surdoc_id, campo, orden) *
    from revisiones
    order by surdoc_id, campo, orden, fecha desc, id desc
),
umbral as (
    select coalesce((select valor::numeric from parametros where clave = 'umbral_confianza'), 0.8) as valor
)
select
    n.surdoc_id,
    n.campo,
    n.orden,
    coalesce(rv.valor_corregido, n.valor_normalizado) as valor,
    case
        when rv.id is not null then 'revisado'
        when n.confianza < (select valor from umbral) or n.valor_normalizado = 'otro' then 'en_revision'
        else 'propuesto'
    end as estado,
    n.valor_normalizado as valor_propuesto,
    n.metodo,
    n.confianza,
    n.modelo,
    n.version_prompt,
    n.origen,
    n.entrada,
    n.justificacion,
    rv.fecha as revisado_en
from ultima_normalizacion n
left join ultima_revision rv using (surdoc_id, campo, orden);

create or replace view fichas_publicas with (security_invoker = true) as
select
    r.surdoc_id,
    m.nombre as museo,
    r.titulo,
    r.numero_inventario,
    r.clasificacion,
    r.coleccion,
    r.objeto,
    r.descripcion,
    r.dimensiones,
    r.tecnica_material,
    r.cultura_originaria,
    r.cultura_arqueologica,
    r.area_cultural,
    r.area_geografica,
    r.estado_conservacion,
    r.url_imagen,
    r.credito_imagen,
    'https://www.surdoc.cl/registro/' || r.surdoc_id as url_ficha
from registros r
join museos m on m.id = r.museo_id
where not r.dado_de_baja;

create or replace view cola_revision with (security_invoker = true) as
select
    v.surdoc_id, v.campo, v.orden, v.valor_propuesto, v.metodo, v.confianza, v.modelo,
    v.version_prompt, v.origen, v.entrada, v.justificacion,
    f.objeto, f.tecnica_material, f.descripcion, f.url_ficha
from valor_vigente v
join fichas_publicas f using (surdoc_id)
where v.estado = 'en_revision';

alter table categorias enable row level security;
alter table parametros enable row level security;

drop policy if exists lectura_publica on categorias;
create policy lectura_publica on categorias for select to anon, authenticated using (true);
drop policy if exists lectura_publica on parametros;
create policy lectura_publica on parametros for select to anon, authenticated using (true);

grant select on categorias, parametros, valor_vigente, fichas_publicas, cola_revision
    to anon, authenticated;
revoke insert, update, delete, truncate on categorias, parametros, valor_vigente,
    fichas_publicas, cola_revision from anon, authenticated;
