import serial
import time

class Packet:

    def __init__(self, frame):
        self.frame = frame

    def __str__(self):
        return " ".join("{:02x}".format(byte) for byte in self.frame)

    def toSignedInt(self, raw, decimals=0):
        val = round(int.from_bytes(raw, byteorder="little", signed=True) / pow(10, decimals), decimals)
        return int(val) if decimals == 0 else val

    def toUnsignedInt(self, raw, decimals=0):
        val = round(int.from_bytes(raw, byteorder="little", signed=False) / pow(10, decimals), decimals)
        return int(val) if decimals == 0 else val


class HouseCurrent(Packet):
    def __str__(self):
        return "{0}  {1:.1f} A house current".format(super().__str__(),
            self.toSignedInt(self.frame[6:8], 1))

class VehicleVoltage(Packet):
    def __str__(self):
        return "{0}  {1:.1f} V vehicle voltage".format(super().__str__(),
            self.toUnsignedInt(self.frame[6:8], 2))

class HouseVoltage(Packet):
    def __str__(self):
        return "{0}  {1:.1f} V house voltage".format(super().__str__(),
            self.toUnsignedInt(self.frame[6:8], 2))

class HouseCapacityAmpHours(Packet):
    def __str__(self):
        return "{0}  {1} Ah house capacity".format(super().__str__(),
            self.toUnsignedInt(self.frame[6:8]))

class HouseCapacityPercent(Packet):
    def __str__(self):
        return "{0}  {1} % house capacity".format(super().__str__(),
            self.toUnsignedInt(self.frame[6:7]))

class FreshPercent(Packet):
    def __str__(self):
        return "{0}  {1} % fresh water".format(super().__str__(),
            self.toUnsignedInt(self.frame[6:8]))

class GrayPercent(Packet):
    def __str__(self):
        return "{0}  {1} % gray water".format(super().__str__(),
            self.toUnsignedInt(self.frame[6:8]))


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
        elif frame[3] == 0x14 and frame[5] == 0x02:
            return FreshPercent(frame)
        elif frame[3] == 0x18 and frame[5] == 0x02:
            return GrayPercent(frame)
        elif frame[3] == 0x44 and frame[5] == 0x03:
            return VehicleVoltage(frame)
    return Packet(frame)

class Reader:

    def __init__(self, port):
        self.bytes_buffer = b""
        self.serial = serial.Serial(port, 19200, timeout=1, bytesize=8, stopbits=1, parity=serial.PARITY_EVEN)

    def write(self, data):
        self.serial.write(data)

    def buffer(self, byte):
        self.bytes_buffer += bytes([byte])

    def read_byte(self):
        if len(self.bytes_buffer):
            byte = self.bytes_buffer[0]
            self.bytes_buffer = self.bytes_buffer[1:]
        else:
            byte = self.serial.read()
            byte = byte[0] if len(byte) else None
        return byte

    def read_packet(self):
        start_byte = None
        while start_byte != 0xaa:
            start_byte = self.read_byte()
        contents = b""
        next_byte = None
        while next_byte != 0xaa:
            next_byte = self.read_byte()
            if next_byte is not None:
                contents += bytes([next_byte])
        # We have an excessive 0xaa at the end. Remove it from contents and put it into the buffer.
        self.buffer(contents[-1])
        contents = contents[:-1]
        # Return the packet.
        packet = parse_packet(bytes([start_byte]) + contents)
        return packet

    def dump(self):
        count = 0
        start = time.time()
        while True:
            packet_start = time.time()
            packet = self.read_packet()
            count += 1
            print("{0:11.6f}  {1}".format(packet_start - start, packet), flush=True)
            # After every 10th packet, request the house voltage.
            if count % 10 == 0:
                self.write(b"\xaa\x22\x0c\xf4\x03\x06\x00\x00\x20")

    def help_understand(self):
        counts = {}
        while True:
            packet = self.format_packet(self.read_packet())
            counts[packet] = (counts[packet] if packet in counts else 0) + 1
            print("\x1b[2J\x1b[H")
            for packet in sorted(counts):
                print("{0}  x {1}".format(packet, counts[packet]))

if __name__ == "__main__":
    # TODO: Hardcoded port for my local machine.
    reader = Reader("/dev/ttyS7")
    reader.dump()
