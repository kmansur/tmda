"""Regression tests for legacy MTA exit status and delivery semantics."""
import importlib
import sys
import types
import unittest
from unittest.mock import patch


class MTADeliveryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import TMDA
        cls.previous_defaults = getattr(TMDA, "Defaults", None)
        cls.previous_mta = getattr(TMDA, "MTA", None)
        cls.saved_module = sys.modules.get("TMDA.MTA")
        cls.saved_deliver = sys.modules.get("TMDA.Deliver")
        defaults = types.ModuleType("TMDA.Defaults")
        cls.module_patch = patch.dict(sys.modules, {"TMDA.Defaults": defaults})
        cls.module_patch.start()
        TMDA.Defaults = defaults
        sys.modules.pop("TMDA.MTA", None)
        cls.module = importlib.import_module("TMDA.MTA")

    @classmethod
    def tearDownClass(cls):
        import TMDA
        sys.modules.pop("TMDA.MTA", None)
        if cls.saved_module is not None:
            sys.modules["TMDA.MTA"] = cls.saved_module
        if cls.saved_deliver is None:
            sys.modules.pop("TMDA.Deliver", None)
        else:
            sys.modules["TMDA.Deliver"] = cls.saved_deliver
        cls.module_patch.stop()
        if cls.previous_defaults is None:
            if hasattr(TMDA, "Defaults"):
                delattr(TMDA, "Defaults")
        else:
            TMDA.Defaults = cls.previous_defaults
        if cls.previous_mta is None:
            if hasattr(TMDA, "MTA"):
                delattr(TMDA, "MTA")
        else:
            TMDA.MTA = cls.previous_mta

    def test_factory_retains_original_mta_types(self):
        for name, kind in (
            ("postfix", self.module.Postfix),
            ("exim", self.module.Exim),
            ("sendmail", self.module.Sendmail),
            ("qmail", self.module.Qmail),
        ):
            with self.subTest(mta=name):
                self.assertIsInstance(self.module.init(name, "/tmp/mailbox"), kind)

    def test_delivery_exit_statuses_by_mta(self):
        for name, hard, temp, stop in (
            ("postfix", 77, 75, 0),
            ("exim", 77, 75, 0),
            ("sendmail", 77, 75, 0),
            ("qmail", 100, 111, 99),
        ):
            mta = self.module.init(name, "/tmp/mailbox")
            for method, expected in (("bounce", hard), ("defer", temp),
                                     ("stop", stop)):
                with self.subTest(mta=name, method=method):
                    with self.assertRaises(SystemExit) as raised:
                        getattr(mta, method)()
                    self.assertEqual(raised.exception.code, expected)

    def test_filter_mode_stop_preserves_exit_status(self):
        for name, expected in (("postfix", 99), ("qmail", 99)):
            with self.subTest(mta=name):
                mta = self.module.init(name, "_filter_")
                with self.assertRaises(SystemExit) as raised:
                    mta.stop()
                self.assertEqual(raised.exception.code, expected)

    def test_postfix_delivery_delegates_instruction_and_exits_success(self):
        with patch.object(self.module.Deliver, "Deliver") as delivery:
            mta = self.module.init("postfix", "/tmp/mbox")
            with self.assertRaises(SystemExit) as raised:
                mta.deliver("message", "/tmp/other")
        self.assertEqual(raised.exception.code, 0)
        delivery.assert_called_once_with("message", "/tmp/other")
        delivery.return_value.deliver.assert_called_once_with()

    def test_qmail_qok_does_not_write_another_message(self):
        with patch.object(self.module.Deliver, "Deliver") as delivery:
            mta = self.module.init("qmail", "/tmp/mbox")
            with self.assertRaises(SystemExit) as raised:
                mta.deliver("message", "_qok_")
        self.assertEqual(raised.exception.code, 0)
        delivery.assert_not_called()

    def test_qmail_delivery_stops_after_success(self):
        with patch.object(self.module.Deliver, "Deliver") as delivery:
            mta = self.module.init("qmail", "/tmp/mbox")
            with self.assertRaises(SystemExit) as raised:
                mta.deliver("message")
        self.assertEqual(raised.exception.code, 99)
        delivery.assert_called_once_with("message", "/tmp/mbox")
        delivery.return_value.deliver.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
