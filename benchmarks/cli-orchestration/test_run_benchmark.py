#!/usr/bin/env python3
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path


SCRIPT = Path(__file__).with_name("run_benchmark.py")
SPEC = importlib.util.spec_from_file_location("run_benchmark", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
SPEC.loader.exec_module(MODULE)


class JsonExtractionTests(unittest.TestCase):
    def test_object_beats_number_embedded_in_prose(self) -> None:
        text = 'Searching for ticket T-17.\n{"id":"T-17","priority":2}'
        self.assertEqual(MODULE.extract_json_value(text), {"id": "T-17", "priority": 2})


if __name__ == "__main__":
    unittest.main()
