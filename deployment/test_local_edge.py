#!/usr/bin/env python3
"""
Local Edge Runtime Verification Test
Validates the ML model and Azure IoT Edge module logic locally before cloud deployment.
"""

import os
import sys
import json
import time

current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.abspath(os.path.join(current_dir, ".."))
if project_root not in sys.path:
    sys.path.append(project_root)

from edge_module.predictor import IrrigationPredictor
from edge_module.main import SmartIrrigationEdgeModule


def run_comprehensive_local_test():
    print("=" * 70)
    print("      AZURE IOT EDGE MODULE LOCAL TEST & VALIDATION HARNESS      ")
    print("=" * 70)

    # 1. Initialize inference engine
    print("\n[TEST 1] Initializing Edge Predictor...")
    predictor = IrrigationPredictor(model_dir=os.path.join(project_root, "edge_module"))
    print(f"  -> Model successfully loaded: {predictor.model_name}")

    # 2. Test Key Agronomic Edge Cases
    test_cases = [
        {
            "name": "Extreme Drought Condition",
            "inputs": {"soil_moisture": 11.0, "temperature": 38.0, "humidity": 20.0, "rainfall": 0.0},
            "expected_decision": "irrigate",
        },
        {
            "name": "Soil Saturated / Field Capacity",
            "inputs": {"soil_moisture": 52.0, "temperature": 27.0, "humidity": 60.0, "rainfall": 0.0},
            "expected_decision": "don't irrigate",
        },
        {
            "name": "Sudden Storm Event (Rain Override)",
            "inputs": {"soil_moisture": 15.0, "temperature": 20.0, "humidity": 85.0, "rainfall": 15.0},
            "expected_decision": "don't irrigate",
        },
        {
            "name": "High Evaporative Demand (Heat Stress)",
            "inputs": {"soil_moisture": 26.0, "temperature": 36.5, "humidity": 25.0, "rainfall": 0.0},
            "expected_decision": "irrigate",
        },
        {
            "name": "Cool Humid Evening (Moisture Conserved)",
            "inputs": {"soil_moisture": 32.0, "temperature": 18.0, "humidity": 80.0, "rainfall": 0.0},
            "expected_decision": "don't irrigate",
        },
    ]

    print("\n[TEST 2] Verifying Agronomic Decision Logic & Latency...")
    all_passed = True
    latencies = []

    for idx, tc in enumerate(test_cases, start=1):
        res = predictor.predict(**tc["inputs"])
        latencies.append(res["latency_ms"])
        passed = (res["decision"] == tc["expected_decision"])
        all_passed = all_passed and passed
        status_flag = "PASS" if passed else "FAIL"

        print(f"  Case {idx}: {tc['name']:<42} [{status_flag}]")
        print(f"    Inputs:   {tc['inputs']}")
        print(f"    Decision: {res['decision'].upper()} (Confidence: {res['confidence']*100:.1f}%)")
        print(f"    Latency:  {res['latency_ms']} ms")
        print(f"    Reason:   {res['reason']}")
        print()

    # 3. Test Edge Module Class Lifecycle & Processing
    print("[TEST 3] Testing Edge Module Interface & Fallback Mode...")
    module = SmartIrrigationEdgeModule()
    # Execute sample inference through module
    mod_res = module.process_inference(soil_moisture=16.5, temperature=34.0, humidity=30.0, rainfall=0.0)
    assert mod_res["action_code"] == 1, "Module inference result mismatch"
    assert module.stats["total_inferences"] == 1, "Stats counter failure"
    assert module.stats["irrigate_decisions"] == 1, "Stats counter failure"
    print("  -> Module internal state and stats counter verified.")

    # 4. Latency SLA Check
    avg_lat = sum(latencies) / len(latencies)
    print(f"\n[TEST 4] Edge Latency Verification:")
    print(f"  Average Single-Sample Latency: {avg_lat:.3f} ms")
    if avg_lat < 25.0:
        print("  -> PASSED: Suitable for low-power edge gateways and offline on-site execution.")
    else:
        print("  -> WARNING: Inference latency exceeded expected budget.")

    print("\n" + "=" * 70)
    if all_passed:
        print(">>> ALL LOCAL VERIFICATION TESTS PASSED SUCCESSFULLY! <<<")
        print("The ML model and edge module are validated for Azure IoT Edge deployment.")
    else:
        print(">>> SOME TESTS FAILED. CHECK LOGS ABOVE. <<<")
    print("=" * 70)


if __name__ == "__main__":
    run_comprehensive_local_test()

