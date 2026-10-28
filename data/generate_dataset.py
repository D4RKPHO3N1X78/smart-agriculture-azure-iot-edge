#!/usr/bin/env python3
"""
Synthetic Dataset Generator for Smart Agriculture Irrigation Decision Model
Scenario: Low-connectivity agricultural edge nodes requiring on-site irrigation decisions.
Ground truth modeled after FAO-56 Irrigation and Drainage guidelines.

Features:
- soil_moisture (%): Current soil volumetric water content (0 - 100%)
- temperature (°C): Ambient field temperature (10 - 45 °C)
- humidity (%): Ambient relative humidity (15 - 95 %)
- rainfall (mm): Recent precipitation / rain forecast (0 - 50 mm)

Output:
- irrigation_action (0: don't irrigate, 1: irrigate)
"""

import os
import numpy as np
import pandas as pd


def generate_irrigation_dataset(
    n_samples: int = 4000, random_state: int = 42
) -> pd.DataFrame:
    """Generates synthetic agronomy-backed irrigation decision data."""
    np.random.seed(random_state)

    # 1. Environmental distributions
    # Soil moisture: Beta distribution covering 8% to 55%
    soil_moisture = np.random.beta(a=2.8, b=3.0, size=n_samples) * 47.0 + 8.0

    # Temperature: Gaussian centered around 27.5°C, clipped to [10, 46]
    temperature = np.random.normal(loc=27.5, scale=7.0, size=n_samples)
    temperature = np.clip(temperature, 10.0, 46.0)

    # Humidity: Inversely correlated with temperature (daytime physics)
    humidity_base = 88.0 - (temperature - 10.0) * 1.5
    humidity_noise = np.random.normal(loc=0.0, scale=10.0, size=n_samples)
    humidity = np.clip(humidity_base + humidity_noise, 15.0, 95.0)

    # Rainfall: Zero-inflated distribution (most days have no rain)
    is_rainy = np.random.binomial(n=1, p=0.25, size=n_samples)
    rain_amount = np.random.exponential(scale=8.0, size=n_samples) * is_rainy
    rainfall = np.clip(rain_amount, 0.0, 50.0)

    # 2. FAO-56 Agronomic decision logic
    # - Field Capacity: ~32% - 40% (no irrigation needed)
    # - Permanent Wilting Point: ~10% - 14%
    # - Management Allowed Depletion (MAD) trigger: ~22% - 25% (depending on ET demand)
    # - Significant Rainfall (>= 4.0 mm): suspends irrigation

    irrigation_actions = []
    for sm, temp, hum, rain in zip(soil_moisture, temperature, humidity, rainfall):
        # Physical hard constraints:
        if rain >= 4.0:
            # External water supplied by precipitation
            action = 0
        elif sm >= 34.0:
            # Soil has abundant moisture (field capacity)
            action = 0
        elif sm <= 18.0 and rain < 2.0:
            # Critical wilting risk
            action = 1
        else:
            # Intermediate zone: 18% < sm < 34%
            # Moisture deficit: 0.0 at sm=34%, 1.0 at sm=18%
            moisture_deficit = (34.0 - sm) / 16.0

            # Atmospheric Evapotranspiration (ET) demand:
            # High temp + dry air = higher ET -> accelerates irrigation need
            # Cool temp + moist air = lower ET -> delays irrigation
            et_demand = (temp - 24.0) / 20.0 - (hum - 50.0) / 60.0

            # Rain mitigation
            rain_mitigation = rain / 2.5

            stress_index = (moisture_deficit * 1.6) + (et_demand * 0.9) - (rain_mitigation * 2.0)

            # Sigmoid boundary around threshold 1.0
            prob = 1.0 / (1.0 + np.exp(-3.5 * (stress_index - 0.95)))
            action = 1 if prob >= 0.50 else 0

        irrigation_actions.append(action)

    df = pd.DataFrame(
        {
            "soil_moisture": np.round(soil_moisture, 2),
            "temperature": np.round(temperature, 2),
            "humidity": np.round(humidity, 2),
            "rainfall": np.round(rainfall, 2),
            "irrigation_action": irrigation_actions,
        }
    )

    return df


if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(current_dir, "smart_irrigation_data.csv")

    df = generate_irrigation_dataset(n_samples=4000, random_state=42)
    df.to_csv(output_path, index=False)

    print(f"Generated dataset successfully saved to: {output_path}")
    print(f"Total records: {len(df)}")
    print("Class distribution:")
    class_counts = df["irrigation_action"].value_counts()
    print(
        f" - Don't irrigate (0): {class_counts.get(0, 0)} ({class_counts.get(0, 0)/len(df)*100:.1f}%)"
    )
    print(
        f" - Irrigate (1):       {class_counts.get(1, 0)} ({class_counts.get(1, 0)/len(df)*100:.1f}%)"
    )
    print("\nSummary Statistics:")
    print(df.describe().to_string())
