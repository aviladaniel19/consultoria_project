{# Usa el esquema de la carpeta (estandarizado/analitico) tal cual, sin el prefijo del target. #}
{% macro generate_schema_name(custom_schema_name, node) -%}
    {{ custom_schema_name if custom_schema_name else target.schema }}
{%- endmacro %}


{#
  Versión vigente de cada registro en la capa de origen:
  - solo ejecuciones aprobadas (las 'failed_quality' quedan en cuarentena)
  - la carga más reciente gana cuando la llave se repite
  Devuelve las columnas: rec (jsonb), _loaded_at, _run_id
#}
{% macro origen_vigente(fuente, llave) %}
    select v._record as rec, v._loaded_at, v._run_id
    from (
        select b.*,
               row_number() over (
                   partition by {% for k in llave %}b._record ->> '{{ k }}'{% if not loop.last %}, {% endif %}{% endfor %}
                   order by b._loaded_at desc, b._id desc
               ) as _rn
        from {{ source('origen', fuente) }} b
        join {{ source('meta', 'runs') }} r on r.run_id = b._run_id
        where r.status in ('success', 'success_with_warnings')
    ) v
    where v._rn = 1
{% endmacro %}


{# Conversiones seguras: valores que no cumplen el formato quedan NULL en vez de romper el modelo. #}
{% macro a_numero(expr) -%}
    case when trim({{ expr }}) ~ '^-?[0-9]+(\.[0-9]+)?([eE][-+]?[0-9]+)?$' then trim({{ expr }})::numeric end
{%- endmacro %}

{% macro a_fecha(expr) -%}
    case when {{ expr }} ~ '^\d{4}-\d{2}-\d{2}' then ({{ expr }})::timestamp end
{%- endmacro %}
