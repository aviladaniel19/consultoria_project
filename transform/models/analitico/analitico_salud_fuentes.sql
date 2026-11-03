{{ config(alias='salud_fuentes') }}

-- Tablero genérico de la plataforma: sirve para cualquier fuente registrada.
with ult as (
    select distinct on (source_name)
           source_name, status as ultimo_estado, finished_at as ultima_ejecucion,
           records_loaded as ultimos_registros
    from {{ source('meta', 'runs') }}
    order by source_name, started_at desc
),
agg as (
    select source_name,
           count(*)                                                        as ejecuciones_30d,
           avg((status in ('success', 'success_with_warnings'))::int)      as tasa_exito_30d,
           sum(records_loaded)                                             as registros_30d,
           avg(extract(epoch from finished_at - started_at))               as duracion_media_s
    from {{ source('meta', 'runs') }}
    where started_at >= now() - interval '30 days'
    group by source_name
),
reglas as (
    select q.source_name,
           count(*) filter (where not q.passed)                            as reglas_incumplidas_30d
    from {{ source('meta', 'quality_results') }} q
    join {{ source('meta', 'runs') }} r using (run_id)
    where r.started_at >= now() - interval '30 days'
    group by q.source_name
)
select s.name as fuente, s.type as tipo, s.tags, s.enabled as activa,
       ult.ultimo_estado, ult.ultima_ejecucion, ult.ultimos_registros,
       agg.ejecuciones_30d, agg.tasa_exito_30d, agg.registros_30d, agg.duracion_media_s,
       coalesce(reglas.reglas_incumplidas_30d, 0) as reglas_incumplidas_30d,
       st.cursor_value as cursor_actual
from {{ source('meta', 'sources') }} s
left join ult    on ult.source_name = s.name
left join agg    on agg.source_name = s.name
left join reglas on reglas.source_name = s.name
left join {{ source('meta', 'state') }} st on st.source_name = s.name
