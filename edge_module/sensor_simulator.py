#!/usr/bin/env python3
"""
Simulated Edge Sensor Module for Smart Agriculture
Generates realistic dynamic diurnal field telemetry:
- Morning dew / moderate moisture
- Midday solar heating and rapid soil drying
- Sudden rainfall storm event
- Post-rainfall recovery

Can run standalone or as an Azure IoT Edge simulated sensor module.
"""

import os
import sys
import time
import json
import random
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [SensorSim] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("SensorSimulator")

try:
    from azure.iot.device.aio import IoTHubModuleClient
    from azure.iot.device import Message
    AZURE_SDK_AVAILABLE = True
except ImportError:
    AZURE_SDK_AVAILABLE = False


class SensorSimulator:
    """Simulates realistic dynamic weather and soil sensors."""

    def __init__(self):
        # Initial baseline conditions
        self.soil_moisture = 32.0  # percentage
        self.temperature = 22.0    # celsius
        self.humidity = 68.0       # percentage
        self.rainfall = 0.0        # mm
        self.step = 0

    def generate_next_reading(self) -> dict:
        """Simulates changing environmental conditions over time."""
        self.step += 1

        # Phase 1 (Steps 1-3): Morning / Mild conditions
        if self.step <= 3:
            self.temperature = 22.0 + random.uniform(-0.5, 1.0)
            self.humidity = 65.0 + random.uniform(-2.0, 2.0)
            self.soil_moisture -= random.uniform(0.1, 0.4)
            self.rainfall = 0.0
            phase_desc = "Morning: Mild conditions, adequate moisture"

        # Phase 2 (Steps 4-7): Heat wave / Sun peak -> soil drying out
        elif self.step <= 7:
            self.temperature = 34.0 + random.uniform(0.0, 3.5)
            self.humidity = 28.0 + random.uniform(-3.0, 3.0)
            self.soil_moisture -= random.uniform(2.5, 4.0)
            self.soil_moisture = max(11.0, self.soil_moisture)
            self.rainfall = 0.0
            phase_desc = "Midday Peak Heat: Soil drying out, high evapotranspiration"

        # Phase 3 (Steps 8-10): Sudden storm / precipitation event
        elif self.step <= 10:
            self.temperature = 21.0 + random.uniform(-1.0, 1.0)
            self.humidity = 90.0 + random.uniform(-2.0, 4.0)
            self.rainfall = random.uniform(8.0, 18.0)
            self.soil_moisture += self.rainfall * 1.5
            self.soil_moisture = min(58.0, self.soil_moisture)
            phase_desc = "Afternoon Storm: Heavy rain shower in progress"

        # Phase 4 (Steps 11+): Post-storm / saturated soil
        else:
            self.temperature = 24.0 + random.uniform(-0.5, 1.5)
            self.humidity = 78.0 + random.uniform(-3.0, 3.0)
            self.rainfall = 0.0
            self.soil_moisture -= random.uniform(0.2, 0.6)
            phase_desc = "Post-Rain: Soil saturated / field capacity"

        return {
            "device_id": "sensor-probe-alpha-01",
            "soil_moisture": round(self.soil_moisture, 2),
            "temperature": round(self.temperature, 2),
            "humidity": round(self.humidity, 2),
            "rainfall": round(self.rainfall, 2),
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "scenario_phase": phase_desc,
        }


async def run_standalone_test(total_iterations: int = 12, delay_sec: float = 1.0):
    """Feeds simulated readings directly into the ML Predictor locally."""
    from predictor import IrrigationPredictor

    predictor = IrrigationPredictor()
    sim = SensorSimulator()

    logger.info("=" * 65)
    logger.info("STARTING LOCAL SENSOR TELEMETRY & EDGE DECISION TEST")
    logger.info("=" * 65)

    for i in range(1, total_iterations + 1):
        reading = sim.generate_next_reading()
        logger.info(f"\n[Step {i:02d}] {reading['scenario_phase']}")
        logger.info(
            f"  Sensors => Soil: {reading['soil_moisture']}% | "
            f"Temp: {reading['temperature']}°C | "
            f"Humidity: {reading['humidity']}% | "
            f"Rainfall: {reading['rainfall']}mm"
        )

        decision_result = predictor.predict(
            soil_moisture=reading["soil_moisture"],
            temperature=reading["temperature"],
            humidity=reading["humidity"],
            rainfall=reading["rainfall"],
        )

        badge = "[*** IRRIGATE ***]" if decision_result["action_code"] == 1 else "[DO NOT IRRIGATE]"
        logger.info(
            f"  Action  => {badge} (Confidence: {decision_result['confidence']*100:.1f}%, "
            f"Latency: {decision_result['latency_ms']}ms)"
        )
        logger.info(f"  Reason  => {decision_result['reason']}")

        await asyncio.sleep(delay_sec)

    logger.info("\n" + "=" * 65)
    logger.info("LOCAL SENSOR SIMULATION TEST COMPLETED SUCCESSFULLY!")
    logger.info("=" * 65)


if __name__ == "__main__":
    current_dir = os.path.dirname(os.path.abspath(__file__))
    if current_dir not in sys.path:
        sys.path.append(current_dir)

    asyncio.run(run_standalone_test(total_iterations=12, delay_sec=0.2))

