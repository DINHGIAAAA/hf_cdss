import json
import sys

from app.modules.datastores.service import bootstrap_datastores


def main() -> int:
    results = bootstrap_datastores()
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(result.get("status") == "ok" for result in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())

