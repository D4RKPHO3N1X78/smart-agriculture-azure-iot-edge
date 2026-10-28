#!/usr/bin/env python3
"""
Irrigation Predictor Engine for Azure IoT Edge Module
Provides fast, lightweight, on-site edge inference without requiring cloud connectivity.
"""

import os
import time
import json
from datetime import datetime, timezone
from typing import Dict, Any, Tuple, Optional
import joblib
import pandas as pd


class IrrigationPredictor:
    """Edge inference engine for agricultural irrigation classification."""

    def __init__(self, model_dir: Optional[str] = None):
        if model_dir is None:
            model_dir = os.path.dirname(os.path.abspath(__file__))

        self.model_path = os.path.join(model_dir, "irrigation_model.joblib")
        self.metadata_path = os.path.join(model_dir, "model_metadata.json")

        if not os.path.exists(self.model_path):
            raise FileNotFoundError(f"Model file not found at: {self.model_path}")

        # Load trained pipeline
        start_time = time.perf_counter()
        self.pipeline = joblib.load(self.model_path)
        load_time_ms = (time.perf_counter() - start_time) * 1000.0

        # Load metadata if present
        self.metadata = {}
        if os.path.exists(self.metadata_path):
            with open(self.metadata_path, "r") as f:
                self.metadata = json.load(f)

        self.model_name = self.metadata.get("model_type", "ScikitLearn-Pipeline")
        self.feature_names = self.metadata.get(
            "features", ["soil_moisture", "temperature", "humidity", "rainfall"]
        )

        print(
            f"[IrrigationPredictor] Model '{self.model_name}' loaded in {load_time_ms:.2f}ms"
        )

    def _validate_inputs(
        self,
        soil_moisture: float,
        temperature: float,
        humidity: float,
        rainfall: float,
    ) -> Tuple[float, float, float, float]:
        """Validates and clips sensor inputs within physically plausible boundaries."""
        sm = float(max(0.0, min(100.0, soil_moisture)))
        temp = float(max(-20.0, min(65.0, temperature)))
        hum = float(max(0.0, min(100.0, humidity)))
        rain = float(max(0.0, rainfall))
        return sm, temp, hum, rain

    def _generate_agronomy_reason(
        self,
        decision: str,
        confidence: float,
        soil_moisture: float,
        temperature: float,
        humidity: float,
        rainfall: float,
    ) -> str:
        """Constructs a clear, agronomic explanation for farm operators."""
        if decision == "irrigate":
            if rainfall >= 5.0:
                return f"Sensor readings indicate irrigation despite recent precipitation ({rainfall:.1f}mm). Review rain gauge."
            if soil_moisture < 20.0:
                return (
                    f"Soil moisture critically low ({soil_moisture:.1f}%). "
                    f"Elevated atmospheric demand (Temp: {temperature:.1f}°C, Hum: {humidity:.1f}%). Immediate irrigation required."
                )
            return (
                f"High evapotranspiration rate (Temp: {temperature:.1f}°C, Hum: {humidity:.1f}%) "
                f"depleting moderate soil moisture ({soil_moisture:.1f}%). Irrigation advised."
            )
        else:
            if rainfall >= 5.0:
                return f"Significant recent or ongoing rainfall detected ({rainfall:.1f}mm). Irrigation suspended to prevent waterlogging."
            if soil_moisture >= 45.0:
                return f"Soil moisture is at field capacity / saturated ({soil_moisture:.1f}%). No irrigation required."
            return (
                f"Adequate moisture retention ({soil_moisture:.1f}%) under mild evaporative demand "
                f"(Temp: {temperature:.1f}°C, Hum: {humidity:.1f}%). Conserving water."
            )

    def predict(
        self,
        soil_moisture: float,
        temperature: float,
        humidity: float,
        rainfall: float,
    ) -> Dict[str, Any]:
        """Runs single-sample inference and returns structured decision."""
        sm, temp, hum, rain = self._validate_inputs(
            soil_moisture, temperature, humidity, rainfall
        )

        input_df = pd.DataFrame(
            [[sm, temp, hum, rain]], columns=self.feature_names
        )

        start_time = time.perf_counter()
        pred_class = int(self.pipeline.predict(input_df)[0])
        probabilities = self.pipeline.predict_proba(input_df)[0]
        latency_ms = (time.perf_counter() - start_time) * 1000.0

        decision = "irrigate" if pred_class == 1 else "don't irrigate"
        confidence = float(probabilities[pred_class])

        reason = self._generate_agronomy_reason(
            decision=decision,
            confidence=confidence,
            soil_moisture=sm,
            temperature=temp,
            humidity=hum,
            rainfall=rain,
        )

        now_iso = datetime.now(timezone.utc).isoformat()

        return {
            "decision": decision,
            "action_code": pred_class,
            "confidence": round(confidence, 4),
            "probability_irrigate": round(float(probabilities[1]), 4),
            "probability_dont_irrigate": round(float(probabilities[0]), 4),
            "features": {
                "soil_moisture": sm,
                "temperature": temp,
                "humidity": hum,
                "rainfall": rain,
            },
            "reason": reason,
            "latency_ms": round(latency_ms, 3),
            "model_type": self.model_name,
            "timestamp": now_iso,
        }


if __name__ == "__main__":
    predictor = IrrigationPredictor()
    test_cases = [
        {"soil_moisture": 14.2, "temperature": 35.0, "humidity": 28.0, "rainfall": 0.0},
        {"soil_moisture": 48.0, "temperature": 25.0, "humidity": 65.0, "rainfall": 0.0},
        {"soil_moisture": 16.0, "temperature": 22.0, "humidity": 80.0, "rainfall": 12.0},
        {"soil_moisture": 26.5, "temperature": 38.0, "humidity": 25.0, "rainfall": 0.0},
    ]

    print("\n--- Testing Edge Inference Engine Locally ---")
    for tc in test_cases:
        res = predictor.predict(**tc)
        print(
            f"Input: {tc} => Decision: [{res['decision'].upper()}] (Conf: {res['confidence']*100:.1f}%, Latency: {res['latency_ms']}ms)"
        )
        print(f"  Reason: {res['reason']}\n")
