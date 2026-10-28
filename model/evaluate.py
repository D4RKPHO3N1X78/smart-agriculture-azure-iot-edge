#!/usr/bin/env python3
"""
Detailed Model Evaluation Script for Smart Agriculture Irrigation Decision Model
Calculates metrics, plots/displays confusion matrix, ROC-AUC, and edge latency benchmarks.
"""

import os
import json
import time
import numpy as np
import pandas as pd
import joblib
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
    classification_report,
)


def evaluate():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, ".."))
    model_path = os.path.join(current_dir, "irrigation_model.joblib")
    data_path = os.path.join(project_root, "data", "smart_irrigation_data.csv")

    if not os.path.exists(model_path):
        raise FileNotFoundError(f"Model not found at {model_path}. Run train.py first.")
    if not os.path.exists(data_path):
        raise FileNotFoundError(f"Data not found at {data_path}. Run generate_dataset.py first.")

    model = joblib.load(model_path)
    df = pd.read_csv(data_path)

    features = ["soil_moisture", "temperature", "humidity", "rainfall"]
    X = df[features]
    y = df["irrigation_action"]

    # Latency benchmark
    latencies = []
    for _ in range(100):
        sample = X.iloc[[np.random.randint(0, len(X))]]
        t0 = time.perf_counter()
        _ = model.predict(sample)
        latencies.append((time.perf_counter() - t0) * 1000.0)

    avg_latency = np.mean(latencies)
    p95_latency = np.percentile(latencies, 95)

    y_pred = model.predict(X)
    y_prob = model.predict_proba(X)[:, 1]

    acc = accuracy_score(y, y_pred)
    prec = precision_score(y, y_pred)
    rec = recall_score(y, y_pred)
    f1 = f1_score(y, y_pred)
    auc = roc_auc_score(y, y_prob)
    cm = confusion_matrix(y, y_pred)

    print("=======================================================")
    print("      SMART AGRICULTURE IRRIGATION MODEL EVALUATION    ")
    print("=======================================================")
    print(f"Total Dataset Records Evaluated: {len(df)}")
    print(f"Accuracy:           {acc * 100:.2f}%")
    print(f"Precision:          {prec * 100:.2f}%")
    print(f"Recall:             {rec * 100:.2f}%")
    print(f"F1 Score:           {f1 * 100:.2f}%")
    print(f"ROC-AUC:            {auc:.4f}")
    print(f"Average Latency:    {avg_latency:.3f} ms")
    print(f"P95 Edge Latency:   {p95_latency:.3f} ms")
    print("\nConfusion Matrix:")
    print(f"                 Predicted 0 (No)    Predicted 1 (Irrigate)")
    print(f"Actual 0 (No)        {cm[0, 0]:<15d}     {cm[0, 1]:<15d}")
    print(f"Actual 1 (Irrigate)  {cm[1, 0]:<15d}     {cm[1, 1]:<15d}")
    print("\nDetailed Classification Report:")
    print(classification_report(y, y_pred, target_names=["Don't Irrigate", "Irrigate"]))
    print("=======================================================")


if __name__ == "__main__":
    evaluate()
