import importlib.util
import unittest
from pathlib import Path
from unittest.mock import call, patch


MIGRATION = Path(__file__).parents[1] / "alembic" / "versions" / "c87d380fc50a_add_discovery_tables.py"


class DiscoveryMigrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        spec = importlib.util.spec_from_file_location("discovery_migration", MIGRATION)
        cls.module = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(cls.module)

    def test_revision_extends_current_v1_head(self):
        self.assertEqual(self.module.revision, "c87d380fc50a")
        self.assertEqual(self.module.down_revision, "a71c8d9e4f20")

    def test_upgrade_creates_both_tables(self):
        with patch.object(self.module.op, "create_table") as create_table, patch.object(
            self.module.op, "create_index"
        ):
            self.module.upgrade()
        self.assertEqual([item.args[0] for item in create_table.call_args_list], ["discovery_runs", "discovered_devices"])

    def test_downgrade_removes_tables_in_dependency_order(self):
        with patch.object(self.module.op, "drop_table") as drop_table:
            self.module.downgrade()
        self.assertEqual(
            drop_table.call_args_list,
            [call("discovered_devices"), call("discovery_runs")],
        )


if __name__ == "__main__":
    unittest.main()
