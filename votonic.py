import serial
import time

class Reader:

    def __init__(self, port):
        self.bytes_buffer = b""
        self.serial = serial.Serial(port, 19200, timeout=1, bytesize=8, stopbits=1, parity=serial.PARITY_EVEN)

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
        return bytes([start_byte]) + contents

    def format_packet(self, packet):
        return " ".join("{:02x}".format(byte) for byte in packet)

    def dump(self):
        start = time.time()
        while True:
            packet_start = time.time()
            packet = self.format_packet(self.read_packet())
            print("{0:11.6f}  {1}".format(packet_start - start, packet), flush=True)

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
