
import os
import tempfile
import unittest
from pathlib import Path

import database


class ValidationQueueTest(unittest.TestCase):
    def setUp(self):
        self.temp_file = tempfile.NamedTemporaryFile(
            suffix=".db",
            delete=False,
        )
        self.temp_file.close()

        self.original_db_path = database.DB_PATH
        database.DB_PATH = Path(self.temp_file.name)
        database.init_db()

        self.ticket_id = database.save_ticket({
            "description": "Test support ticket",
            "status": "OPEN",
        })

    def tearDown(self):
        database.DB_PATH = self.original_db_path

        for suffix in ("", "-journal", "-wal", "-shm"):
            path = self.temp_file.name + suffix
            if os.path.exists(path):
                try:
                    os.remove(path)
                except PermissionError:
                    pass

    def test_pending_validation_is_counted(self):
        database.record_ticket_validation_start(self.ticket_id)

        self.assertEqual(
            database.count_pending_ticket_validations(),
            1,
        )

    def test_multiple_pending_validations_are_counted(self):
        second_ticket_id = database.save_ticket({
            "description": "Second test support ticket",
            "status": "OPEN",
        })

        database.record_ticket_validation_start(self.ticket_id)
        database.record_ticket_validation_start(second_ticket_id)

        self.assertEqual(
            database.count_pending_ticket_validations(),
            2,
        )

    def test_completed_validation_is_not_counted(self):
        event_id = database.record_ticket_validation_start(
            self.ticket_id
        )
        database.complete_ticket_validation(event_id, True)

        self.assertEqual(
            database.count_unfinished_validation_events(),
            0,
        )

    def test_rejected_validation_is_not_counted(self):
        event_id = database.record_ticket_validation_start(
            self.ticket_id
        )
        database.complete_ticket_validation(event_id, False)

        self.assertEqual(
            database.count_unfinished_validation_events(),
            0,
        )


if __name__ == "__main__":
    unittest.main()
