{{ config(alias='secop_procesos') }}

with vigente as (
    {{ origen_vigente('secop_procesos', ['id_del_proceso']) }}
)

select
    rec ->> 'id_del_proceso'                              as id_proceso,
    rec ->> 'referencia_del_proceso'                      as referencia,
    rec ->> 'entidad'                                     as entidad,
    rec ->> 'nit_entidad'                                 as nit_entidad,
    rec ->> 'departamento_entidad'                        as departamento,
    rec ->> 'ciudad_entidad'                              as ciudad,
    rec ->> 'modalidad_de_contratacion'                   as modalidad,
    rec ->> 'estado_del_procedimiento'                    as estado,
    {{ a_numero("rec ->> 'precio_base'") }}               as precio_base,
    {{ a_fecha("rec ->> 'fecha_de_publicacion_del'") }}   as fecha_publicacion,
    _loaded_at                                            as cargado_en,
    _run_id                                               as run_id
from vigente
