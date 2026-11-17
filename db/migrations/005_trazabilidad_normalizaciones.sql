-- 005_trazabilidad_normalizaciones.sql
-- Trazabilidad de cada valor normalizado (RNF-03):
--   origen:  de dónde salió el valor que se normalizó.
--            'termino'     = un valor de la ficha (registro_terminos), ej. "Piedra"
--            'campo'       = un campo simple de la ficha, ej. estado de conservación
--            'descripcion' = la ficha no declara el dato y se infirió de la descripción
--   entrada: texto exacto que se evaluó (lo que vio la regla o el LLM).
-- Idempotente.

alter table normalizaciones add column if not exists origen text not null default 'termino'
    check (origen in ('termino', 'campo', 'descripcion'));
alter table normalizaciones add column if not exists entrada text;
-- Hash de los campos de la ficha (registros_raw.hash_campos) al momento de normalizar:
-- si la ficha cambia en SURDOC, el hash deja de coincidir y el valor vuelve a quedar pendiente.
alter table normalizaciones add column if not exists hash_ficha text;

comment on column normalizaciones.origen is
    'termino: valor de registro_terminos; campo: campo simple de registros; descripcion: inferido de la descripción porque la ficha no lo declara.';
comment on column normalizaciones.entrada is 'Texto exacto evaluado por la regla o el LLM.';
comment on column normalizaciones.hash_ficha is 'hash_campos de la ficha evaluada; si difiere del actual, el valor está pendiente.';
