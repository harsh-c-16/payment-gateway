"""Generate/check the four owned JSON Schemas: python -m projectctl.schemas --check."""

import argparse
import json

from jsonschema import Draft202012Validator

from projectctl.config import ROOT
from projectctl.models import EvaluationConfig, FixtureManifest, RunManifest, Summary

SCHEMAS = {
    "config": EvaluationConfig,
    "run": RunManifest,
    "summary": Summary,
    "fixture": FixtureManifest,
}


def schema_documents():
    for name, model in SCHEMAS.items():
        document = model.model_json_schema()
        document["$schema"] = "https://json-schema.org/draft/2020-12/schema"
        document["$id"] = f"urn:group3:evaluation:{name}:1"
        Draft202012Validator.check_schema(document)
        yield name, json.dumps(document, ensure_ascii=False, indent=2) + "\n"


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, allow_abbrev=False)
    parser.add_argument("--check", action="store_true", help="fail if checked-in schemas differ")
    args = parser.parse_args(argv)
    mismatches = []
    for name, content in schema_documents():
        path = ROOT / "contracts" / "evaluation" / f"{name}.schema.json"
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                mismatches.append(name)
        else:
            path.write_text(content, encoding="utf-8")
    print(json.dumps({"schemas": list(SCHEMAS), "mismatches": mismatches, "checked": args.check}))
    return 3 if mismatches else 0


if __name__ == "__main__":
    raise SystemExit(main())
