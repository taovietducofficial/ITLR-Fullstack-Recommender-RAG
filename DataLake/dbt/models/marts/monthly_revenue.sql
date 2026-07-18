select
    d.year,
    d.month,
    count(distinct f.order_id) as orders,
    sum(f.price) as revenue,
    sum(f.freight_value) as freight
from {{ source('gold', 'fact_table') }} f
join {{ source('gold', 'dim_date') }} d on f.datekey = d.datekey
group by d.year, d.month
