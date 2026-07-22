select
    category,
    count(*) as interactions,
    count(distinct user_id) as distinct_users,
    count(distinct item_id) as distinct_courses
from {{ source('gold', 'itlr_fact_interaction') }}
group by 1
order by interactions desc
