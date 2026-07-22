select
    event_type,
    count(*) as events,
    count(distinct user_id) as distinct_users
from {{ source('gold', 'itlr_fact_interaction') }}
group by 1
