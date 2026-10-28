#!/usr/bin/env python3
"""
Live Edge Gateway Runner for Smart Agriculture ML Irrigation System
Runs the ML model locally and streams decision telemetry to Azure IoT Hub:
Hub: iothub-smart-irrigation-8921
Device: irrigation-edge-01
"""

import os
import sys
import time
import json
import asyncio
import logging

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [EdgeGateway] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("LiveGateway")

from edge_module.predictor import IrrigationPredictor
from edge_module.sensor_simulator import SensorSimulator

try:
    from azure.iot.device.aio import IoTHubDeviceClient
    from azure.iot.device import Message
    AZURE_SDK = True
except ImportError:
    AZURE_SDK = False

# Device connection string from Azure IoT Hub
DEVICE_CONNECTION_STRING = (
    "HostName=iothub-smart-irrigation-8921.azure-devices.net;"
    "DeviceId=irrigation-edge-01;"
    "SharedAccessKey=aqBYf3nYeJ35io5pAxWzXt57/mhFu2jnxl9OIbUatvo="
)


async def main():
    print("=" * 70)
    print("    LIVE EDGE GATEWAY: SMART AGRICULTURE IRRIGATION RUNNER       ")
    print("    Connected to Azure IoT Hub: iothub-smart-irrigation-8921     ")
    print("    Device ID: irrigation-edge-01                                ")
    print("=" * 70)

    # 1. Load ML Model
    logger.info("Initializing local ML inference engine...")
    predictor = IrrigationPredictor(model_dir=os.path.join(os.path.dirname(__file__), "edge_module"))
    logger.info(f"Model successfully loaded: {predictor.model_name}")

    # 2. Connect to Azure IoT Hub
    client = None
    if AZURE_SDK:
        logger.info("Connecting to Azure IoT Hub via WebSockets (Port 443)...")
        client = IoTHubDeviceClient.create_from_connection_string(
            DEVICE_CONNECTION_STRING, websockets=True
        )
        await client.connect()
        logger.info(">>> SUCCESS: Device is ONLINE and connected to Azure IoT Hub! <<<")

        # Report initial Twin state
        reported_patch = {
            "device_status": "ONLINE",
            "model_type": predictor.model_name,
            "offline_autonomous_mode": True,
            "gateway_host": "macbook-edge-node",
            "last_boot": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }
        await client.patch_twin_reported_properties(reported_patch)
        logger.info("Reported properties synchronized with Azure IoT Hub Device Twin.")

    # 3. Simulate continuous sensor readings and on-site ML decisions
    sim = SensorSimulator()
    logger.info("\nStarting autonomous field monitoring loop (Ctrl+C to stop)...\n")

    step = 0
    try:
        while True:
            step += 1
            sensor_data = sim.generate_next_reading()
            
            # Local ML inference (offline on-site, <1ms)
            decision = predictor.predict(
                soil_moisture=sensor_data["soil_moisture"],
                temperature=sensor_data["temperature"],
                humidity=sensor_data["humidity"],
                rainfall=sensor_data["rainfall"],
            )

            # Print on-site edge decision
            action_badge = (
                "[*** ACTION: OPEN VALVES (IRRIGATE) ***]"
                if decision["action_code"] == 1
                else "[=== ACTION: CLOSE VALVES (HOLD) ===]"
            )
            print("-" * 70)
            logger.info(f"[Cycle {step:02d}] Scenario: {sensor_data['scenario_phase']}")
            logger.info(
                f"Sensors: Soil={sensor_data['soil_moisture']}% | "
                f"Temp={sensor_data['temperature']}°C | "
                f"Hum={sensor_data['humidity']}% | "
                f"Rain={sensor_data['rainfall']}mm"
            )
            logger.info(
                f"Decision: {action_badge} (Confidence: {decision['confidence']*100:.1f}%, "
                f"Latency: {decision['latency_ms']}ms)"
            )
            logger.info(f"Reason:   {decision['reason']}")

            # Send telemetry message to Azure IoT Hub
            if client:
                payload = {
                    "deviceId": "irrigation-edge-01",
                    "telemetry": sensor_data,
                    "decision": decision["decision"],
                    "action_code": decision["action_code"],
                    "confidence": decision["confidence"],
                    "reason": decision["reason"],
                    "latency_ms": decision["latency_ms"],
                    "model": predictor.model_name,
                    "timestamp": decision["timestamp"],
                }
                msg = Message(json.dumps(payload))
                msg.content_encoding = "utf-8"
                msg.content_type = "application/json"
                msg.custom_properties["priority"] = "HIGH" if decision["action_code"] == 1 else "NORMAL"
                msg.custom_properties["action"] = decision["decision"]

                await client.send_message(msg)
                logger.info("Telemetry and ML decision successfully dispatched to Azure IoT Hub!")

            await asyncio.sleep(4.0)

    except (KeyboardInterrupt, asyncio.CancelledError):
        logger.info("Stopping gateway...")
    finally:
        if client:
            await client.disconnect()
            logger.info("Disconnected from Azure IoT Hub.")


if __name__ == "__main__":
    asyncio.run(main())
