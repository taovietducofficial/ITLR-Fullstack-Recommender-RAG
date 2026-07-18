to_mysql:
	docker exec -it de_mysql mysql -u"${MYSQL_USER}" -p"${MYSQL_PASSWORD}" ${MYSQL_DATABASE}

to_mysql_root:
	docker exec -it de_mysql mysql -u"root" -p"${MYSQL_ROOT_PASSWORD}" ${MYSQL_DATABASE}

mysql_create:
	docker exec -it de_mysql mysql --local_infile -u"${MYSQL_USER}" -p"${MYSQL_PASSWORD}" ${MYSQL_DATABASE} -e"source /tmp/load_dataset/mysql_datasource.sql"

mysql_load:
	docker exec -it de_mysql mysql --local_infile -u"${MYSQL_USER}" -p"${MYSQL_PASSWORD}" ${MYSQL_DATABASE} -e"source /tmp/load_dataset/mysql_load.sql"

to_psql:
	docker exec -it de_psql psql postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB}

to_psql_no_db:
	docker exec -it de_psql psql postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/postgres

psql_create:
	docker exec -it de_psql psql postgres://${POSTGRES_USER}:${POSTGRES_PASSWORD}@${POSTGRES_HOST}:${POSTGRES_PORT}/${POSTGRES_DB} -f /tmp/load_dataset/psql_datasource.sql -a

to_trino:
	docker exec -it trino trino --catalog lakehouse

register_cdc:
	curl -s -X POST -H "Content-Type: application/json" --data @cdc/register-mysql-connector.json http://localhost:8083/connectors

cdc_status:
	curl -s http://localhost:8083/connectors/olist-cdc/status

stream_cdc:
	docker exec -d spark-master spark-submit --master spark://spark-master:7077 --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.3.2 --executor-memory 1G --total-executor-cores 1 /streaming/cdc_to_bronze.py

stream_cdc_tables:
	docker exec -d spark-master spark-submit --master spark://spark-master:7077 --executor-memory 1G --total-executor-cores 1 /streaming/cdc_to_tables.py

# ponytail: installs dbt-trino on every run to avoid maintaining a custom image; bake a Dockerfile if this gets slow
dbt_build:
	docker run --rm --network data_network -v "$(CURDIR)/dbt:/dbt" -w /dbt python:3.11-slim sh -c "pip install -q dbt-trino && dbt build --profiles-dir ."