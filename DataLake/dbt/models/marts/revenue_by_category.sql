select
    p.product_category_name_english as category,
    count(distinct f.order_id) as orders,
    sum(f.price) as revenue
from {{ source('gold', 'fact_table') }} f
join {{ source('gold', 'dim_product') }} p on f.product_id = p.product_id
group by 1
