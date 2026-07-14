import unittest

from telegram_notifier import UsageReport, build_usage_message


class TelegramNotifierTest(unittest.TestCase):
    def test_build_usage_message_includes_summary_and_errors(self) -> None:
        message = build_usage_message(
            UsageReport(
                user="khanhlinh3009",
                action="Dán link",
                source="Pasted links",
                total_records=3,
                success_records=2,
                error_records=1,
                errors=["RuntimeError: video unavailable"],
            )
        )

        self.assertIn("User: khanhlinh3009", message)
        self.assertIn("Action: Dán link", message)
        self.assertIn("Total records: 3", message)
        self.assertIn("Success: 2", message)
        self.assertIn("Errors: 1", message)
        self.assertIn("RuntimeError: video unavailable", message)


if __name__ == "__main__":
    unittest.main()
