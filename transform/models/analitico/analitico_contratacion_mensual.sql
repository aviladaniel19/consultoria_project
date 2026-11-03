{{ config(alias='contratacion_mensual') }}

select
    date_trunc('month', fecha_publicacion)::date                       as mes,
    coalesce(departamento, 'Sin dato')                                  as departamento,
    coalesce(modalidad, 'Sin dato')                                     as modalidad,
    count(*)                                                            as n_procesos,
    sum(precio_base)                                                    as precio_base_total,
    percentile_cont(0.5) within group (order by precio_base)            as precio_base_mediana,
    avg(precio_base)                                                    as precio_base_media
from {{ ref('estandarizado_secop_procesos') }}
where fecha_publicacion is not null
group by 1, 2, 3
