"""Export the frozen training aggregates needed by the deployed demo."""
from __future__ import annotations

import hashlib
import json
import sqlite3

from .demo import DEPLOY_DB, FROZEN_SETTING
from .final_test import verify_freeze
from .prepare import DB_PATH


def main() -> None:
    frozen = verify_freeze()
    if frozen["setting"] != FROZEN_SETTING.key:
        raise RuntimeError("Unexpected frozen setting")
    DEPLOY_DB.parent.mkdir(parents=True, exist_ok=True)
    temporary = DEPLOY_DB.with_suffix(".tmp")
    temporary.unlink(missing_ok=True)
    with sqlite3.connect(f"file:{DB_PATH}?mode=ro", uri=True) as source, sqlite3.connect(temporary) as target:
        target.executescript("""
            CREATE TABLE train_catalog(product TEXT PRIMARY KEY, display_name TEXT NOT NULL, basket_count INTEGER NOT NULL);
            CREATE TABLE train_directional_stats(
                antecedent TEXT NOT NULL, candidate TEXT NOT NULL, pair_count INTEGER NOT NULL,
                support REAL NOT NULL, confidence REAL NOT NULL, lift REAL NOT NULL,
                PRIMARY KEY(antecedent,candidate));
        """)
        target.executemany("INSERT INTO train_catalog VALUES (?,?,?)", source.execute(
            "SELECT product,display_name,basket_count FROM train_catalog ORDER BY product"))
        target.executemany("INSERT INTO train_directional_stats VALUES (?,?,?,?,?,?)", source.execute(
            "SELECT antecedent,candidate,pair_count,support,confidence,lift "
            "FROM train_directional_stats WHERE pair_count >= 3 ORDER BY antecedent,candidate"))
        target.commit()
        target.execute("VACUUM")
    temporary.replace(DEPLOY_DB)
    digest = hashlib.sha256(DEPLOY_DB.read_bytes()).hexdigest()
    (DEPLOY_DB.parent / "manifest.json").write_text(json.dumps({
        "setting": frozen["setting"], "sha256": digest,
        "source_database_sha256": frozen["sha256"]["data/processed/basket_completion.sqlite"],
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Exported {DEPLOY_DB} ({DEPLOY_DB.stat().st_size:,} bytes; sha256 {digest})")


if __name__ == "__main__":
    main()
