import serial
import time

class Packet:

    def __init__(self, frame):
        self.frame = frame

    def __str__(self):
        return " ".join("{:02x}".format(byte) for byte in self.frame)

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
            "percent": self.toUnsignedInt(self.frame[6:7]),
            "unknown": self.toUnsignedInt(self.frame[7:8]),
        }
    def __str__(self):
        val = self.val()
        return "{0}  {1} % house capacity ({2})".format(super().__str__(), val["percent"], val["unknown"])

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

    def __init__(self, port):
        self.serial = serial.Serial(port, 19200, timeout=1, bytesize=8, stopbits=1, parity=serial.PARITY_EVEN)

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
        self.write(without_checksum + bytes([checksum]))

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
        stats["UsageCurrent"] = stats["HouseCurrent"] - stats["SolarCurrent"]
        return stats

    def slow_stats(self):
        stats = self.get_stats(
            SolarCurrent,
            HouseCurrent,
            HouseCapacityAmpHours,
            HouseCapacityPercent,
            HouseVoltage,
            VehicleVoltage,
        )
        return {**self.fast_stats(), **stats}

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
                return parse_packet(everything)

    def dump(self):
        count = 0
        start = time.time()
        while True:
            packet_start = time.time()
            packet = self.read_packet()
            count += 1
            print("{0:11.6f}  {1}".format(packet_start - start, packet), flush=True)

    def help_understand(self):
        counts = {}
        while True:
            packet = str(self.read_packet())
            counts[packet] = (counts[packet] if packet in counts else 0) + 1
            print("\x1b[2J\x1b[H")
            for packet in sorted(counts):
                if counts[packet] > 1:
                    print("{0}  x {1}".format(packet, counts[packet]))

if __name__ == "__main__":
    # TODO: Hardcoded port for my local machine.
    interface = Interface("/dev/ttyS7")
    interface.dump()
