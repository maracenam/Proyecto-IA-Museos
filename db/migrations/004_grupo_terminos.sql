-- 004_grupo_terminos.sql
-- En Técnica / Material, cada div.technical-item de SURDOC es un grupo "técnica - material",
-- y un grupo puede traer varios materiales separados por coma (ej. 16-919: "Piedra, Cuero").
-- `grupo` guarda la posición del technical-item, para saber qué técnica va con qué material.
-- `orden` sigue siendo correlativo por campo dentro de la ficha. Idempotente.

alter table registro_terminos add column if not exists grupo integer check (grupo >= 0);

comment on column registro_terminos.grupo is
    'Posición del par técnica-material (div.technical-item) en la ficha; null para objeto y nombre alternativo.';
