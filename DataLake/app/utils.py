import os

import mlflow

from text_clean import clean_text

mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow_server:5000"))

model_name = "classification"
model_version = 1

vector_name = "transform"
vector_version = 1

model = mlflow.sklearn.load_model(model_uri=f"models:/{model_name}/{model_version}")
vector = mlflow.sklearn.load_model(model_uri=f"models:/{vector_name}/{vector_version}")


def predict(text):
    text = clean_text(text)
    text_vectorized = vector.transform([text])
    prediction = model.predict(text_vectorized)
    proba = model.predict_proba(text_vectorized)
    max_proba = max(proba[0])
    return prediction, max_proba
