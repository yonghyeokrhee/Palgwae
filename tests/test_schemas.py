from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

import jsonschema
import yaml

from palgwae.builder import build_bundle


ROOT = Path(__file__).resolve().parents[1]
SPEC = ROOT / "examples" / "retail_pipeline" / "context-graph.yaml"
GOLDEN = ROOT / "examples" / "retail_pipeline" / "golden.yaml"
SCHEMAS = ROOT / "ontology" / "schemas"


class PublicSchemaTest(unittest.TestCase):
    def test_schema_ids_are_pinned_to_the_v0_1_0_release(self):
        for schema_path in SCHEMAS.glob("*.schema.json"):
            schema = json.loads(schema_path.read_text(encoding="utf-8"))
            self.assertEqual(
                schema["$id"],
                "https://raw.githubusercontent.com/yonghyeokrhee/"
                f"Palgwae/v0.1.0/ontology/schemas/{schema_path.name}",
            )

    def test_generated_bundle_and_golden_example_match_public_schemas(self):
        with tempfile.TemporaryDirectory() as temporary:
            bundle_dir = Path(temporary) / "bundle"
            build_bundle(SPEC, bundle_dir)

            record_schemas = {
                "nodes.jsonl": "node.schema.json",
                "claims.jsonl": "claim.schema.json",
                "evidence.jsonl": "evidence.schema.json",
                "unresolved.jsonl": "unresolved.schema.json",
            }
            for data_name, schema_name in record_schemas.items():
                schema = json.loads(
                    (SCHEMAS / schema_name).read_text(encoding="utf-8")
                )
                for line in (bundle_dir / data_name).read_text(
                    encoding="utf-8"
                ).splitlines():
                    if line:
                        jsonschema.validate(json.loads(line), schema)

            jsonschema.validate(
                json.loads(
                    (bundle_dir / "manifest.json").read_text(encoding="utf-8")
                ),
                json.loads(
                    (SCHEMAS / "manifest.schema.json").read_text(
                        encoding="utf-8"
                    )
                ),
            )
            jsonschema.validate(
                yaml.safe_load(GOLDEN.read_text(encoding="utf-8")),
                json.loads(
                    (SCHEMAS / "golden.schema.json").read_text(encoding="utf-8")
                ),
            )


if __name__ == "__main__":
    unittest.main()
