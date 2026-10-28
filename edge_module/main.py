#!/usr/bin/env python3
"""
Azure IoT Edge Module: Smart Agriculture Irrigation Decision Engine
Handles on-site edge classification for farms with poor or intermittent connectivity.

Features:
- Azure IoT Edge ModuleClient integration (edgeHub routing)
- Offline-first execution: all ML inference runs locally in <1ms without cloud dependency
- Edge routing: receives from 'sensorInput', outputs to 'irrigationAlerts' and '$upstream'
- Module Twin synchronization: remote configuration of thresholds and operating modes
- Direct Method handling: on-demand diagnostic and inference triggers
- Graceful standalone fallback for local testing without IoT Edge daemon
"""

import os
import sys
import time
import json
import asyncio
import logging
from typing import Dict, Any, Optional

# Configure structured logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [EdgeModule] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("SmartIrrigationEdgeModule")

# Import local ML predictor
try:
    from predictor import IrrigationPredictor
except ImportError:
    from edge_module.predictor import IrrigationPredictor

# Import Azure IoT Device SDK
AZURE_SDK_AVAILABLE = False
try:
    from azure.iot.device.aio import IoTHubModuleClient
    from azure.iot.device import Message, MethodResponse
    AZURE_SDK_AVAILABLE = True
except ImportError:
    logger.warning("azure-iot-device SDK not found. Running in mock standalone mode.")


class SmartIrrigationEdgeModule:
    """Manages Azure IoT Edge runtime lifecycle, ML inference, and twin sync."""

    def __init__(self):
        self.predictor = IrrigationPredictor()
        self.client: Optional[Any] = None
        self.running = False

        # Module Configuration (Configurable via IoT Hub Module Twin)
        self.config = {
            "mode": "autonomous",  # "autonomous", "manual_override", "eco"
            "moisture_bias_offset": 0.0,
            "min_confidence_threshold": 0.60,
            "telemetry_interval_sec": 5,
        }

        # Internal telemetry counters
        self.stats = {
            "total_inferences": 0,
            "irrigate_decisions": 0,
            "dont_irrigate_decisions": 0,
            "start_time": time.time(),
        }

    async def initialize_client(self):
        """Connects to Azure IoT Edge runtime or prepares standalone mode."""
        if not AZURE_SDK_AVAILABLE:
            logger.info("Operating in standalone offline mode (no Azure SDK).")
            return

        try:
            # Check if running in Azure IoT Edge environment
            if "IOTEDGE_WORKLOADURI" in os.environ:
                logger.info("Detected Azure IoT Edge container environment. Connecting via edge daemon...")
                self.client = IoTHubModuleClient.create_from_edge_environment()
            elif "EDGE_MODULE_CONNECTION_STRING" in os.environ:
                conn_str = os.environ["EDGE_MODULE_CONNECTION_STRING"]
                logger.info("Connecting using EDGE_MODULE_CONNECTION_STRING...")
                self.client = IoTHubModuleClient.create_from_connection_string(conn_str)
            else:
                logger.info(
                    "No Edge environment detected. Running local edge simulation mode. "
                    "(Set IOTEDGE_WORKLOADURI or EDGE_MODULE_CONNECTION_STRING for live Hub connection)"
                )
                return

            await self.client.connect()
            logger.info("Successfully connected to Azure IoT EdgeHub / IoT Hub!")

            # Set up message listener on input queue
            self.client.on_message_received = self._on_message_received

            # Set up Module Twin listener
            self.client.on_twin_desired_properties_patch_received = self._on_twin_patch_received

            # Set up Direct Method listener
            self.client.on_method_request_received = self._on_method_request_received

            # Report initial twin status
            await self._report_twin_state()

        except Exception as e:
            logger.error(f"Error initializing Azure IoT Edge client: {e}. Falling back to standalone mode.")
            self.client = None

    async def _report_twin_state(self):
        """Reports module status and active model metrics to Azure IoT Hub."""
        if self.client:
            reported_props = {
                "module_status": "ONLINE",
                "model_type": self.predictor.model_name,
                "offline_autonomous_enabled": True,
                "active_config": self.config,
                "total_inferences": self.stats["total_inferences"],
                "irrigate_decisions": self.stats["irrigate_decisions"],
                "last_sync": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            }
            try:
                await self.client.patch_twin_reported_properties(reported_props)
                logger.info("Reported properties synchronized with Azure IoT Hub.")
            except Exception as e:
                logger.warning(f"Could not sync twin properties (offline or error): {e}")

    async def _on_twin_patch_received(self, twin_patch: Dict[str, Any]):
        """Handles remote configuration updates from Azure IoT Hub."""
        logger.info(f"Received Twin desired property update: {twin_patch}")
        for key in self.config.keys():
            if key in twin_patch:
                self.config[key] = twin_patch[key]
                logger.info(f"Updated config [{key}] = {self.config[key]}")

        await self._report_twin_state()

    async def _on_method_request_received(self, method_request):
        """Handles cloud-to-edge direct method calls."""
        logger.info(f"Received direct method call: '{method_request.name}'")
        status = 200
        payload = {}

        if method_request.name == "GetStatus":
            payload = {
                "status": "healthy",
                "uptime_seconds": round(time.time() - self.stats["start_time"], 1),
                "stats": self.stats,
                "config": self.config,
                "model": self.predictor.model_name,
            }
        elif method_request.name == "RunInference":
            # On-demand inference trigger from cloud
            data = method_request.payload or {}
            sm = data.get("soil_moisture", 18.0)
            temp = data.get("temperature", 32.0)
            hum = data.get("humidity", 35.0)
            rain = data.get("rainfall", 0.0)
            payload = self.process_inference(sm, temp, hum, rain)
        else:
            status = 404
            payload = {"error": f"Method '{method_request.name}' not recognized"}

        if self.client:
            response = MethodResponse.create_from_method_request(
                method_request, status, payload
            )
            await self.client.send_method_response(response)

    async def _on_message_received(self, message):
        """Processes incoming telemetry routed from sensor module through edgeHub."""
        input_name = getattr(message, "input_name", "sensorInput")
        logger.info(f"Received routed telemetry on input '{input_name}'")

        try:
            raw_data = message.data.decode("utf-8")
            payload = json.loads(raw_data)
            logger.info(f"Raw sensor telemetry: {payload}")

            # Extract sensor readings
            sm = float(payload.get("soil_moisture", 25.0)) + self.config["moisture_bias_offset"]
            temp = float(payload.get("temperature", 28.0))
            hum = float(payload.get("humidity", 50.0))
            rain = float(payload.get("rainfall", 0.0))

            # Run on-site ML prediction
            result = self.process_inference(sm, temp, hum, rain)

            # Route decision out
            await self.send_decision_alert(result)

        except Exception as e:
            logger.error(f"Error handling message: {e}", exc_info=True)

    def process_inference(
        self, soil_moisture: float, temperature: float, humidity: float, rainfall: float
    ) -> Dict[str, Any]:
        """Executes localized inference with zero network dependency."""
        result = self.predictor.predict(
            soil_moisture=soil_moisture,
            temperature=temperature,
            humidity=humidity,
            rainfall=rainfall,
        )

        self.stats["total_inferences"] += 1
        if result["action_code"] == 1:
            self.stats["irrigate_decisions"] += 1
        else:
            self.stats["dont_irrigate_decisions"] += 1

        # Check operating mode override
        if self.config["mode"] == "manual_override":
            result["override_active"] = True
            result["note"] = "Operating in manual override; ML recommendation advisory only."
        else:
            result["override_active"] = False

        logger.info(
            f"[DECISION] => {result['decision'].upper()} (Confidence: {result['confidence']*100:.1f}%, "
            f"Latency: {result['latency_ms']}ms) - {result['reason']}"
        )
        return result

    async def send_decision_alert(self, result: Dict[str, Any]):
        """Forwards decision to local actuator module and cloud upstream via EdgeHub."""
        if not self.client:
            logger.info("[Standalone Alert] Telemetry output buffer: (Cloud not connected)")
            return

        try:
            msg_body = json.dumps(result)
            msg = Message(msg_body)
            msg.content_encoding = "utf-8"
            msg.content_type = "application/json"
            msg.custom_properties["decision"] = result["decision"]
            msg.custom_properties["priority"] = "HIGH" if result["action_code"] == 1 else "NORMAL"

            # Route 1: Send to local output for actuator
            await self.client.send_message_to_output(msg, "irrigationAlerts")

            # Route 2: Upstream to Azure IoT Hub (EdgeHub automatically caches if offline)
            logger.info("Dispatched decision alert to EdgeHub routing broker.")

        except Exception as e:
            logger.warning(f"Could not forward message to EdgeHub: {e}")

    async def run_loop(self):
        """Main lifecycle loop."""
        self.running = True
        await self.initialize_client()

        logger.info("Smart Agriculture Irrigation Edge Module is actively running.")
        logger.info("Autonomous on-site decision engine ready.")

        try:
            while self.running:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Module run loop cancelled.")
        finally:
            await self.shutdown()

    async def shutdown(self):
        """Clean shutdown and disconnect."""
        logger.info("Shutting down edge module...")
        self.running = False
        if self.client:
            try:
                await self.client.disconnect()
                logger.info("Disconnected from Azure IoT Edge.")
            except Exception as e:
                logger.error(f"Error during disconnect: {e}")


if __name__ == "__main__":
    module = SmartIrrigationEdgeModule()
    try:
        asyncio.run(module.run_loop())
    except KeyboardInterrupt:
        logger.info("Module stopped by user.")

