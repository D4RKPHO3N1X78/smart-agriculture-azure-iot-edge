#!/usr/bin/env python3
"""
Model Training and Optimization Pipeline for Smart Irrigation Decision
Trains, evaluates, and exports an edge-optimized Machine Learning pipeline.

Features:
- soil_moisture (%)
- temperature (°C)
- humidity (%)
- rainfall (mm)

Output:
- irrigation_action (0: don't irrigate, 1: irrigate)
"""

import os
import json
import shutil
import numpy as np
import pandas as pd
import joblib

from sklearn.model_selection import train_test_split, cross_val_score, StratifiedKFold
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    roc_auc_score,
    confusion_matrix,
    classification_report,
)


def train_and_export_model():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    project_root = os.path.abspath(os.path.join(current_dir, ".."))
    data_path = os.path.join(project_root, "data", "smart_irrigation_data.csv")

    if not os.path.exists(data_path):
        raise FileNotFoundError(f"Dataset not found at {data_path}. Run generate_dataset.py first.")

    print(f"Loading dataset from: {data_path}")
    df = pd.read_csv(data_path)

    feature_cols = ["soil_moisture", "temperature", "humidity", "rainfall"]
    target_col = "irrigation_action"

    X = df[feature_cols]
    y = df[target_col]

    # Stratified Train/Test split (80% train, 20% test)
    X_train, X_test, y_train, y_test = train_test_split(
        X, y, test_size=0.20, random_state=42, stratify=y
    )

    print(f"Dataset Split: {len(X_train)} train samples, {len(X_test)} test samples.")

    # Candidate models suitable for low-latency edge inference
    candidates = {
        "RandomForest": RandomForestClassifier(
            n_estimators=100,
            max_depth=10,
            min_samples_split=4,
            min_samples_leaf=2,
            random_state=42,
            n_jobs=1,  # Single thread avoids threadpool overhead on edge CPUs
        ),
        "GradientBoosting": GradientBoostingClassifier(
            n_estimators=100,
            learning_rate=0.08,
            max_depth=4,
            random_state=42,
        ),
        "LogisticRegression": LogisticRegression(
            C=1.0,
            max_iter=1000,
            random_state=42,
        ),
    }

    best_name = None
    best_pipeline = None
    best_cv_f1 = -1.0
    cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

    print("\n--- Model Benchmark (5-Fold Stratified Cross-Validation) ---")
    for name, clf in candidates.items():
        pipeline = Pipeline([
            ("scaler", StandardScaler()),
            ("classifier", clf)
        ])
        cv_scores = cross_val_score(pipeline, X_train, y_train, cv=cv, scoring="f1")
        mean_f1 = np.mean(cv_scores)
        std_f1 = np.std(cv_scores)
        print(f"[*] {name:20s} | Mean CV F1: {mean_f1:.4f} (±{std_f1:.4f})")

        if mean_f1 > best_cv_f1:
            best_cv_f1 = mean_f1
            best_name = name
            best_pipeline = pipeline

    print(f"\nSelected Best Model: {best_name} with CV F1 = {best_cv_f1:.4f}")

    # Train best pipeline on full training set
    best_pipeline.fit(X_train, y_train)

    # Evaluate on held-out test set
    y_pred = best_pipeline.predict(X_test)
    y_prob = best_pipeline.predict_proba(X_test)[:, 1]

    acc = accuracy_score(y_test, y_pred)
    prec = precision_score(y_test, y_pred)
    rec = recall_score(y_test, y_pred)
    f1 = f1_score(y_test, y_pred)
    auc = roc_auc_score(y_test, y_prob)
    cm = confusion_matrix(y_test, y_pred).tolist()
    report = classification_report(y_test, y_pred, target_names=["Don't Irrigate (0)", "Irrigate (1)"], output_dict=True)

    print("\n--- Test Set Evaluation ---")
    print(f"Accuracy:  {acc * 100:.2f}%")
    print(f"Precision: {prec * 100:.2f}%")
    print(f"Recall:    {rec * 100:.2f}%")
    print(f"F1-Score:  {f1 * 100:.2f}%")
    print(f"ROC-AUC:   {auc:.4f}")
    print("\nConfusion Matrix [[TN, FP], [FN, TP]]:")
    print(np.array(cm))

    # Feature Importance (if applicable)
    classifier_step = best_pipeline.named_steps["classifier"]
    feature_importances = {}
    if hasattr(classifier_step, "feature_importances_"):
        for col, imp in zip(feature_cols, classifier_step.feature_importances_):
            feature_importances[col] = round(float(imp), 4)
        print("\nFeature Importances:")
        for col, imp in feature_importances.items():
            print(f" - {col:15s}: {imp * 100:.2f}%")

    # Save model artifact
    model_save_path = os.path.join(current_dir, "irrigation_model.joblib")
    joblib.dump(best_pipeline, model_save_path)
    print(f"\nTrained pipeline saved to: {model_save_path}")

    # Also copy to edge_module directory for self-contained deployment
    edge_model_path = os.path.join(project_root, "edge_module", "irrigation_model.joblib")
    shutil.copyfile(model_save_path, edge_model_path)
    print(f"Edge model artifact copied to: {edge_model_path}")

    # Export model metadata
    metadata = {
        "model_type": best_name,
        "features": feature_cols,
        "target": target_col,
        "classes": {0: "don't irrigate", 1: "irrigate"},
        "train_samples": len(X_train),
        "test_samples": len(X_test),
        "metrics": {
            "cv_f1": round(float(best_cv_f1), 4),
            "test_accuracy": round(float(acc), 4),
            "test_precision": round(float(prec), 4),
            "test_recall": round(float(rec), 4),
            "test_f1": round(float(f1), 4),
            "test_roc_auc": round(float(auc), 4),
            "confusion_matrix": cm,
        },
        "feature_importances": feature_importances,
        "classification_report": report,
    }

    metadata_path = os.path.join(current_dir, "model_metadata.json")
    with open(metadata_path, "w") as f:
        json.dump(metadata, f, indent=2)
    print(f"Model metadata saved to: {metadata_path}")

    # Also copy metadata to edge module
    edge_metadata_path = os.path.join(project_root, "edge_module", "model_metadata.json")
    shutil.copyfile(metadata_path, edge_metadata_path)

    return metadata


if __name__ == "__main__":
    train_and_export_model()
