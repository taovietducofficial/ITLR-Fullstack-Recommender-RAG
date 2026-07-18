# Dagster libraries to run both dagit and the dagster-daemon. Does not
# need to have access to any pipeline code.
FROM python:3.9.16-slim

# Set $DAGSTER_HOME and copy dagster instance and workspace YAML there
ENV DAGSTER_HOME=/opt/dagster/dagster_home
RUN mkdir -p $DAGSTER_HOME && \
mkdir -p $DAGSTER_HOME/storage && \
mkdir -p $DAGSTER_HOME/compute_logs && \
mkdir -p $DAGSTER_HOME/local_artifact_storage

WORKDIR $DAGSTER_HOME
COPY requirements.txt $DAGSTER_HOME
RUN pip install --upgrade pip && pip install -r requirements.txt
