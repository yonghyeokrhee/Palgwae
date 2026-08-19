from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from palgwae_graphify.adapter import adapt_graph, write_candidate_ledger


ROOT = Path(__file__).resolve().parent
REVISION = "1" * 40


class GraphifyAdapterTest(unittest.TestCase):
    def test_candidates_are_quarantined_and_deterministic(self):
        graph = json.loads((ROOT / "fixtures" / "graph.json").read_text())
        repo = ROOT / "fixtures" / "repo"

        first = adapt_graph(
            graph,
            repository="example-pipeline",
            revision=REVISION,
            repo_root=repo,
            graphify_version="0.9.46",
        )
        second = adapt_graph(
            graph,
            repository="example-pipeline",
            revision=REVISION,
            repo_root=repo,
            graphify_version="0.9.46",
        )

        self.assertEqual(first["candidate_digest"], second["candidate_digest"])
        self.assertTrue(first["unresolved"])
        self.assertTrue(all(c["review_status"] == "CANDIDATE" for c in first["claims"]))
        self.assertFalse(any(c.get("accepted") for c in first["claims"]))
        self.assertTrue(
            all(n["candidate_id"].startswith("candidate:graphify:") for n in first["nodes"])
        )
        self.assertEqual(
            {c["proposed_predicate"] for c in first["claims"] if c["promotion_eligible"]},
            {"CONTAINS", "INVOKES"},
        )

    def test_ledger_manifest_declares_zero_accepted_claims(self):
        graph = json.loads((ROOT / "fixtures" / "graph.json").read_text())
        ledger = adapt_graph(
            graph,
            repository="example-pipeline",
            revision=REVISION,
            repo_root=ROOT / "fixtures" / "repo",
            graphify_version="0.9.46",
        )
        with tempfile.TemporaryDirectory() as temporary:
            manifest = write_candidate_ledger(ledger, Path(temporary) / "ledger")

        self.assertEqual(manifest["accepted_claim_count"], 0)
        self.assertEqual(set(manifest["files"]), {
            "candidate-nodes.jsonl",
            "candidate-claims.jsonl",
            "candidate-evidence.jsonl",
            "unresolved.jsonl",
        })

    def test_rejects_llm_augmented_graphs(self):
        graph = json.loads((ROOT / "fixtures" / "graph.json").read_text())
        graph["input_tokens"] = 1
        with self.assertRaisesRegex(ValueError, "must not record LLM tokens"):
            adapt_graph(
                graph,
                repository="example-pipeline",
                revision=REVISION,
                repo_root=ROOT / "fixtures" / "repo",
                graphify_version="0.9.46",
            )

    def test_dangling_extractor_endpoint_is_explicitly_unresolved(self):
        graph = json.loads((ROOT / "fixtures" / "graph.json").read_text())
        graph["edges"][0]["target"] = "missing_extractor_node"

        ledger = adapt_graph(
            graph,
            repository="example-pipeline",
            revision=REVISION,
            repo_root=ROOT / "fixtures" / "repo",
            graphify_version="0.9.46",
        )

        self.assertTrue(
            any(
                item["reason"] == "DANGLING_EXTRACTOR_ENDPOINT"
                for item in ledger["unresolved"]
            )
        )
        self.assertTrue(all(item["review_status"] == "CANDIDATE" for item in ledger["claims"]))


if __name__ == "__main__":
    unittest.main()
