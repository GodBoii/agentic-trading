from dataclasses import FrozenInstanceError
from datetime import datetime
from importlib import import_module
import json
import struct
import unittest

module = import_module("research.15_timestamp_integrity.normalizer")


def row(**changes):
    packet = {"type":"Full Data","security_id":1,"exchange_segment":1,"LTP":"100.00",
              "LTT":"09:15:01","depth":[{"bid_price":100-i*.05,"ask_price":100.1+i*.05,
              "bid_quantity":10+i,"ask_quantity":20+i,"bid_orders":1,"ask_orders":2}
              for i in range(5)]}
    packet.update(changes)
    return {"received_at":"2026-08-31T09:15:02+05:30","security_id":1,
            "exchange_segment":"NSE_EQ","packet_json":json.dumps(packet)}


class NormalizerTests(unittest.TestCase):
    def test_top_quantity_stays_distinct_from_five_level_sum(self):
        packet = module.normalize_decoded_row(row())
        self.assertEqual(packet.best_bid_quantity,10)
        self.assertEqual(packet.bid_quantity_5,60)
        self.assertIsNone(packet.quote_source_age_seconds)
        self.assertIsNone(packet.source_sequence)

    def test_bare_clock_retains_unknown_date_and_timezone(self):
        packet = module.normalize_decoded_row(row())
        self.assertEqual(packet.trade_time_of_day,"09:15:01")
        self.assertIsNone(packet.trade_utc_us)
        self.assertIsNone(packet.signed_receipt_minus_trade_seconds)
        self.assertEqual(packet.capture_scope,"unknown")
        self.assertFalse(packet.original_wire_available)

    def test_negative_offset_is_preserved_for_explicit_epoch(self):
        future = int(datetime.fromisoformat("2026-08-31T09:15:05+05:30").timestamp())
        packet = module.normalize_decoded_row(row(LTT=future))
        self.assertEqual(packet.signed_receipt_minus_trade_seconds,-3)

    def test_timezone_sensitivities_are_separate_from_default(self):
        packet = module.normalize_decoded_row(row())
        self.assertEqual(module.assumed_same_date_offset(packet,basis="Asia/Kolkata"),1)
        self.assertEqual(module.assumed_same_date_offset(packet,basis="UTC"),1-19800)
        self.assertIsNone(packet.trade_utc_us)

    def test_missing_trade_time_preserved(self):
        packet = module.normalize_decoded_row(row(LTT=None))
        self.assertEqual(packet.trade_time_semantics,"missing")

    def test_frozen_observation_cannot_mutate(self):
        packet = module.normalize_decoded_row(row())
        with self.assertRaises(FrozenInstanceError):
            packet.best_bid = 101

    def test_capture_and_packet_identity_must_match(self):
        for changes in ({"security_id":2},{"exchange_segment":2}):
            with self.assertRaises(module.NormalizationError):
                module.normalize_decoded_row(row(**changes))

    def test_crossed_book_fails_closed(self):
        data = row()
        packet = json.loads(data["packet_json"])
        for depth in packet["depth"]:
            depth["ask_price"] -= 1
        data["packet_json"] = json.dumps(packet)
        with self.assertRaisesRegex(module.NormalizationError,"crossed_book"):
            module.normalize_decoded_row(data)

    def test_naive_receipt_fails_closed(self):
        data = row(); data["received_at"]="2026-08-31T09:15:02"
        with self.assertRaises(module.NormalizationError):
            module.normalize_decoded_row(data)

    def test_malformed_time_and_numbers_rejected(self):
        for changes in ({"LTT":"25:15:01"},{"LTT":-1},{"LTP":"nan"},{"LTP":False}):
            with self.assertRaises(module.NormalizationError):
                module.normalize_decoded_row(row(**changes))

    def test_unsorted_prices_and_fractional_quantities_rejected(self):
        for key,value in (("bid_price",101),("bid_quantity",1.5)):
            data=row(); packet=json.loads(data["packet_json"])
            packet["depth"][1][key]=value; data["packet_json"]=json.dumps(packet)
            with self.assertRaises(module.NormalizationError):
                module.normalize_decoded_row(data)

    def test_binary_full_preserves_epoch_and_wire_hash(self):
        timestamp = int(datetime.fromisoformat("2026-08-31T09:15:01+05:30").timestamp())
        depth = b"".join(struct.pack("<IIHHff",10+i,20+i,1,2,100-i*.05,100.1+i*.05)
                         for i in range(5))
        wire = struct.pack("<BHBIfHIfIIIIIIffff100s",8,162,1,1,100,1,timestamp,100,
                           1000,100,200,0,0,0,100,100,101,99,depth)
        result = module.normalize_binary_full(wire,received_at="2026-08-31T09:15:02+05:30")
        self.assertEqual(result.trade_utc_us,timestamp*1000000)
        self.assertEqual(result.signed_receipt_minus_trade_seconds,1)
        self.assertTrue(result.original_wire_available)
        self.assertIsNone(result.quote_event_utc_us)

    def test_short_wire_and_non_full_packets_rejected(self):
        with self.assertRaises(module.NormalizationError):
            module.normalize_binary_full(b"bad",received_at="2026-08-31T09:15:02+05:30")
        with self.assertRaises(module.NormalizationError):
            module.normalize_decoded_row(row(type="Ticker Data"))

    def test_aware_trade_datetime_preserves_signed_microseconds(self):
        packet = module.normalize_decoded_row(row(LTT="2026-08-31T03:45:01.500000+00:00"))
        self.assertEqual(packet.signed_receipt_minus_trade_seconds,.5)
        self.assertEqual(packet.trade_time_semantics,"explicit_aware_datetime")

    def test_invented_quote_time_field_does_not_create_source_provenance(self):
        packet = module.normalize_decoded_row(row(quote_event_time="2026-08-31T09:15:02+05:30"))
        self.assertIsNone(packet.quote_event_utc_us)

    def test_zero_top_quantity_rejected(self):
        data=row(); packet=json.loads(data["packet_json"])
        packet["depth"][0]["ask_quantity"]=0
        data["packet_json"]=json.dumps(packet)
        with self.assertRaisesRegex(module.NormalizationError,"empty_top_depth"):
            module.normalize_decoded_row(data)

    def test_unknown_scope_is_not_promoted_to_complete_capture(self):
        data=row(); data["capture_scope"]="hot_only"
        self.assertEqual(module.normalize_decoded_row(data).capture_scope,"hot_only")
        data["capture_scope"]="complete_according_to_guess"
        with self.assertRaises(module.NormalizationError):
            module.normalize_decoded_row(data)


if __name__ == "__main__":
    unittest.main()
