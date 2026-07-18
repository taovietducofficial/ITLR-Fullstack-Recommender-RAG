import os
import tempfile

import matplotlib.pyplot as plt
import mlflow
import pandas as pd
import seaborn as sns
from dagster import AssetIn, asset
from dotenv import load_dotenv
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import accuracy_score, classification_report, confusion_matrix
from sklearn.model_selection import GridSearchCV, train_test_split

from ..utils.text import clean_text

load_dotenv(".env")
pd.set_option("display.max_colwidth", None)

COMPUTE_KIND = "Mlflow"
LAYER = "ml"


@asset(
    description="Extract review data for machine learning",
    ins={
        "silver_cleaned_order_review": AssetIn(key_prefix=["silver", "orderreview"]),
    },
    key_prefix=["ml", "extract"],
    compute_kind=COMPUTE_KIND,
    group_name=LAYER,
)
def extract(
    context,
    silver_cleaned_order_review,
):
    df1 = silver_cleaned_order_review
    df = df1.toPandas()

    df_comments = df.loc[:, ["review_score", "review_comment_message"]]
    df_comments.columns = ["score", "comment"]

    df_comments["comment"] = df_comments["comment"].apply(lambda x: clean_text(x))

    mapping = {
        1: "negative",
        2: "negative",
        3: "negative",
        4: "positive",
        5: "positive",
    }
    df_comments["score"] = df_comments["score"].map(mapping)

    text_vectorizer = TfidfVectorizer(max_features=15000, use_idf=True, smooth_idf=True)

    X = df_comments["comment"]
    y = df_comments["score"]
    X_pre = text_vectorizer.fit_transform(X)

    param_grid = {
        "C": [0.001, 0.01, 0.1, 1.0, 10.0],
        "penalty": ["l1", "l2"],
        "solver": ["liblinear", "saga"],
    }

    X_train, X_test, y_train, y_test = train_test_split(
        X_pre, y, stratify=y, train_size=0.8, random_state=1
    )
    log = LogisticRegression(max_iter=1000)
    grid_search = GridSearchCV(estimator=log, param_grid=param_grid, scoring="accuracy", cv=5)
    grid_search.fit(X_train, y_train)
    best_params = grid_search.best_params_

    mlflow.set_tracking_uri(os.getenv("MLFLOW_TRACKING_URI", "http://mlflow_server:5000"))
    mlflow.set_experiment("sentiment analysis")
    mlflow.sklearn.autolog()

    with tempfile.TemporaryDirectory() as tmp_dir, mlflow.start_run():
        log = LogisticRegression(max_iter=1000, **best_params)
        log.fit(X_train, y_train)
        y_pred = log.predict(X_test)
        acc = accuracy_score(y_test, y_pred)
        report = classification_report(y_test, y_pred)

        report_path = os.path.join(tmp_dir, "classification_report.txt")
        with open(report_path, "w") as f:
            f.write(report)

        cm = confusion_matrix(y_pred, y_test)
        plt.figure(figsize=(8, 6))
        sns.heatmap(
            cm,
            annot=True,
            cmap="Blues",
            fmt="g",
            xticklabels=["negative", "positive"],
            yticklabels=["negative", "positive"],
        )
        plt.xlabel("Actual labels")
        plt.ylabel("Predict labels")
        plt.title("Confusion Matrix")
        cm_path = os.path.join(tmp_dir, "confusion_matrix.png")
        plt.savefig(cm_path)

        mlflow.log_metrics({"test_accuracy": acc})
        mlflow.log_artifact(cm_path)
        mlflow.log_artifact(report_path)
        mlflow.sklearn.log_model(text_vectorizer, "TF-IDFVectorizer")

