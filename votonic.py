#!/usr/bin/env python3

import argparse
import serial
import signal
import sys
import time
from urllib import request

class Packet:

    def __init__(self, frame):
        self.frame = frame

    def hex(self, data):
        return " ".join("{:02x}".format(byte) for byte in data)

    def __str__(self):
        return "{0} / {1}".format(self.hex(self.frame[1:4]), self.hex(self.frame[5:-1]))

    def val(self):
        return None

    def toSignedInt(self, raw, decimals=0):
        val = round(int.from_bytes(raw, byteorder="little", signed=True) / pow(10, decimals), decimals)
        return int(val) if decimals == 0 else val

    def toUnsignedInt(self, raw, decimals=0):
        val = round(int.from_bytes(raw, byteorder="little", signed=False) / pow(10, decimals), decimals)
        return int(val) if decimals == 0 else val


class SolarCurrent(Packet):
    REQ_HDR = b"\x22\x10\xf4"
    REQ_VAL = b"\x02\x00\x00"
    def val(self):
        return self.toSignedInt(self.frame[6:8], 1)
    def __str__(self):
        return "{0}  {1:.1f} A solar current".format(super().__str__(), self.val())

class HouseCurrent(Packet):
    REQ_HDR = b"\x22\x0c\xf4"
    REQ_VAL = b"\x02\x00\x00"
    def val(self):
        return self.toSignedInt(self.frame[6:8], 1)
    def __str__(self):
        return "{0}  {1:.1f} A house current".format(super().__str__(), self.val())

class VehicleVoltage(Packet):
    REQ_HDR = b"\x22\x44\xf4"
    REQ_VAL = b"\x03\x00\x00"
    def val(self):
        return self.toUnsignedInt(self.frame[6:8], 2)
    def __str__(self):
        return "{0}  {1:.1f} V vehicle voltage".format(super().__str__(), self.val())

class HouseVoltage(Packet):
    REQ_HDR = b"\x22\x0c\xf4"
    REQ_VAL = b"\x03\x00\x00"
    def val(self):
        return self.toUnsignedInt(self.frame[6:8], 2)
    def __str__(self):
        return "{0}  {1:.1f} V house voltage".format(super().__str__(), self.val())

class HouseCapacityAmpHours(Packet):
    REQ_HDR = b"\x22\x0c\xf4"
    REQ_VAL = b"\x05\x00\x00"
    def val(self):
        return self.toUnsignedInt(self.frame[6:8])
    def __str__(self):
        return "{0}  {1} Ah house capacity".format(super().__str__(), self.val())

class HouseCapacityPercent(Packet):
    REQ_HDR = b"\x22\x0c\xf4"
    REQ_VAL = b"\x06\x00\x00"
    def val(self):
        return {
            "Percent": self.toUnsignedInt(self.frame[6:7]),
            "Unknown": self.toUnsignedInt(self.frame[7:8]),
        }
    def __str__(self):
        val = self.val()
        return "{0}  {1} % house capacity ({2})".format(super().__str__(), val["Percent"], val["Unknown"])

class FreshPercent(Packet):
    REQ_HDR = b"\x22\x14\xf4"
    REQ_VAL = b"\x02\x00\x00"
    def val(self):
        return self.toUnsignedInt(self.frame[6:8])
    def __str__(self):
        return "{0}  {1} % fresh water".format(super().__str__(), self.val())

class GrayPercent(Packet):
    REQ_HDR = b"\x22\x18\xf4"
    REQ_VAL = b"\x02\x00\x00"
    def val(self):
        return self.toUnsignedInt(self.frame[6:8])
    def __str__(self):
        return "{0}  {1} % gray water".format(super().__str__(), self.val())


def parse_packet(frame):
    if frame[0:3] == b"\xaa\x62\xf4":
        if frame[3] == 0x0c:
            if frame[5] == 0x02:
                return HouseCurrent(frame)
            elif frame[5] == 0x03:
                return HouseVoltage(frame)
            elif frame[5] == 0x05:
                return HouseCapacityAmpHours(frame)
            elif frame[5] == 0x06:
                return HouseCapacityPercent(frame)
        elif frame[3] == 0x10 and frame[5] == 0x02:
            return SolarCurrent(frame)
        elif frame[3] == 0x14 and frame[5] == 0x02:
            return FreshPercent(frame)
        elif frame[3] == 0x18 and frame[5] == 0x02:
            return GrayPercent(frame)
        elif frame[3] == 0x44 and frame[5] == 0x03:
            return VehicleVoltage(frame)
    return Packet(frame)

class Interface:

    def __init__(self, port, dump=False):
        self.serial = serial.Serial(port, 19200, timeout=1, bytesize=8, stopbits=1, parity=serial.PARITY_EVEN)
        self.start = time.time()
        self.dump = dump

    def checksum(self, data):
        checksum = 0x55
        for byte in data:
            checksum ^= byte
        return checksum

    def write(self, data):
        self.serial.write(data)

    def write_packet(self, header, payload):
        without_checksum = b"\xaa" + header + bytes([len(payload)]) + payload
        checksum = self.checksum(without_checksum)
        checksummed = without_checksum + bytes([checksum])
        if self.dump:
            print(self.dump_format(Packet(checksummed), sent=True), flush=True)
        self.write(checksummed)

    def read_bytes(self, count=1):
        data = b""
        while len(data) < count:
            data += self.serial.read(count - len(data))
        return data

    def request(self, what):
        self.write_packet(what.REQ_HDR, what.REQ_VAL)

    def get(self, what):
        for send_retry in range(3):
            self.request(what)
            for recv_retry in range(10):
                packet = self.read_packet()
                if type(packet) == what:
                    return packet
            time.sleep(0.5)
        return None

    def get_val(self, what):
        packet = self.get(what)
        return None if packet is None else packet.val()

    def get_stats(self, *types):
        result = {}
        for the_type in types:
            result[the_type.__name__] = self.get_val(the_type)
        return result

    def fast_stats(self):
        stats = self.get_stats(
            SolarCurrent,
            HouseCurrent,
        )
        stats["UsageCurrent"] = round(stats["HouseCurrent"] - stats["SolarCurrent"], 1)
        return stats

    def slow_stats(self):
        stats = self.get_stats(
            HouseCapacityAmpHours,
            HouseCapacityPercent,
            HouseVoltage,
            VehicleVoltage,
        )
        return stats

    def water_stats(self):
        interested_in = [FreshPercent, GrayPercent]
        stats = {}
        # Request the stats every 5 seconds to keep the sensors alive.
        # Do that for 30 seconds and then return the values.
        start = time.time()
        while time.time() - start < 30:
            iteration_start = time.time()
            for what in interested_in:
                # print("Requesting", what.__name__)
                self.request(what)
            while time.time() - iteration_start < 5:
                # We have to keep reading packets or the buffer fills up.
                packet = self.read_packet()
                if type(packet) in interested_in:
                    # print("Got", str(packet))
                    stats[type(packet).__name__] = packet.val()
        return stats

    def collect_stats(self, handler=print):
        last_fast = last_slow = last_water = 0
        collect_water_at = 0
        request_water = False
        water_classes = [FreshPercent, GrayPercent]
        while True:
            signal.alarm(30)
            # Keep reading, else the buffer might fill up.
            packet = self.read_packet()
            try:
                if time.time() - last_fast > 10:
                    last_fast = time.time()
                    if request_water:
                        if time.time() > collect_water_at:
                            request_water = False
                            handler(self.get_stats(*water_classes))
                        else:
                            for cls in water_classes:
                                self.request(cls)
                    handler(self.fast_stats())
                if time.time() - last_slow > 600:
                    last_slow = time.time()
                    handler(self.slow_stats())
                if time.time() - last_water > 3600:
                    last_water = time.time()
                    collect_water_at = last_water + 30
                    request_water = True
            except:
                # Better luck next time.
                pass

    @staticmethod
    def flatten_stats(stats):
        flat = {}
        for name, value in stats.items():
            if type(value) == dict:
                for subname, value in value.items():
                    flat[name + subname] = value
            else:
                flat[name] = value
        return flat

    def read_packet(self):
        while True:
            start_byte = None
            while start_byte != b"\xaa":
                start_byte = self.read_bytes(1)
            header = self.read_bytes(3)
            payload_length = self.read_bytes(1)
            contents = self.read_bytes(payload_length[0])
            checksum = self.read_bytes(1)
            everything = start_byte + header + payload_length + contents + checksum
            if self.checksum(everything) == 0:
                # That's a valid packet.
                packet = parse_packet(everything)
                if self.dump:
                    print(self.dump_format(packet), flush=True)
                return packet

    def dump_format(self, packet, sent=False):
        return "{0:11.6f}  {1}  {2}".format(
            time.time() - self.start,
            "-->" if sent else "   ",
            packet,
        )

    def dump(self):
        self.dump = True
        count = 0
        while True:
            packet = self.read_packet()
            count += 1

    def help_understand(self):
        counts = {}
        while True:
            packet = str(self.read_packet())
            counts[packet] = (counts[packet] if packet in counts else 0) + 1
            print("\x1b[2J\x1b[H")
            for packet in sorted(counts):
                if counts[packet] > 1:
                    print("{0}  x {1}".format(packet, counts[packet]))


class IoTPlotterStatsHandler:
    def __init__(self, feed, key):
        self.feed = feed
        self.key = key

    def handler(self, stats):
        lines = []
        print(stats)
        for name, value in Interface.flatten_stats(stats).items():
            lines.append("0,{0},{1}".format(name, value))
        req = request.Request(
            "https://iotplotter.com/api/v2/feed/{0}.csv".format(self.feed),
            data="\n".join(lines).encode(),
            headers={"api-key": self.key},
        )
        request.urlopen(req).read()


if __name__ == "__main__":
    def run_dump(args):
        interface = Interface(args.device)
        interface.dump()

    def run_send(args):
        b = bytes.fromhex(args.hex)
        if len(b) < 3:
            raise ArgumentError("header needs at least 3 bytes")
        if len(b) > 255:
            raise ArgumentError("payload may not exceed 255 bytes")
        interface = Interface(args.device)
        for i in range(args.read_before):
            print(interface.read_packet())
        interface.write_packet(b[0:3], b[3:])
        for i in range(args.read_after):
            print(interface.read_packet())

    def run_collect(args):
        interface = Interface(args.device, dump=args.dump)
        plotter = IoTPlotterStatsHandler(args.feed_id, args.key)
        interface.collect_stats(plotter.handler)

    parser = argparse.ArgumentParser()
    parser.add_argument("--device", "-d", type=str, required=True)
    subparsers = parser.add_subparsers()

    parser_dump = subparsers.add_parser("dump")
    parser_dump.set_defaults(func=run_dump)

    parser_send = subparsers.add_parser("send")
    parser_send.add_argument("--read-before", "-b", type=int, default=0)
    parser_send.add_argument("--read-after", "-a", type=int, default=0)
    parser_send.add_argument("hex", type=str)
    parser_send.set_defaults(func=run_send)

    parser_collect = subparsers.add_parser("collect")
    parser_collect.add_argument("--feed-id", "-f", type=str, required=True)
    parser_collect.add_argument("--key", "-k", type=str, required=True)
    parser_collect.add_argument("--dump", "-v", action="store_true", default=False)
    parser_collect.set_defaults(func=run_collect)

    args = parser.parse_args()
    if not "func" in args:
        parser.print_help(sys.stderr)
        sys.exit(1)

    signal.signal(signal.SIGALRM, lambda sig, stk: sys.exit(2))

    args.func(args)
