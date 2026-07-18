# import mlflow.sklearn
# import streamlit as st
# mlflow.set_tracking_uri("http://mlflow_server:5000")

# model_name = "classification"
# model_version = 1

# vector_name = "transform"
# vector_version = 1

# model = mlflow.sklearn.load_model(model_uri=f"models:/{model_name}/{model_version}")
# vector = mlflow.sklearn.load_model(model_uri=f"models:/{vector_name}/{vector_version}")

# st.write(model)
# st.write(vector)