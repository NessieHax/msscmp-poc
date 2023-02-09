# Copyright (c) 2023-present miku-666
# This software is provided 'as-is', without any express or implied
# warranty. In no event will the authors be held liable for any damages
# arising from the use of this software.
# 
# Permission is granted to anyone to use this software for any purpose,
# including commercial applications, and to alter it and redistribute it
# freely, subject to the following restrictions:
# 
# 1. The origin of this software must not be misrepresented; you must not
#    claim that you wrote the original software. If you use this software
#    in a product, an acknowledgment in the product documentation would be
#    appreciated but is not required.
# 2. Altered source versions must be plainly marked as such, and must not be
#    misrepresented as being the original software.
# 3. This notice may not be removed or altered from any source distribution.
from dataclasses import dataclass, field
from io import SEEK_SET, BufferedReader
from pprint import pprint
import struct, os
from typing import Callable, Any

def log(caller):
    def logger(*args, **kwargs):
        res = caller(*args, **kwargs)
        print(f"{repr(caller.__name__)} returned: {res}")
        return res
    return logger

@dataclass(slots=True)
class BufferedDataReader:
    _stream: BufferedReader
    _endianness: str = field(default='>') # big endian

    @property
    def stream(self) -> BufferedReader:
        return self._stream

    def readInts(self, count: int) -> tuple[int]:
        return struct.unpack(f"{self._endianness}{count}i", self._stream.read(count*4))

    def readInt(self) -> int:
        return self.readInts(1)[0]

    def readFloats(self, count: int) -> tuple[float]:
        return struct.unpack(f"{self._endianness}{count}f", self._stream.read(count*4))

    def readFloat(self) -> float:
        return self.readFloats(1)[0]

    def readUntil(self, stopper: bytes) -> bytes:
        result = bytearray()
        while self._stream.peek(1)[:1] != stopper: result.append(self._stream.read(1)[0])
        return bytes(result)

    def readString(self) -> str:
        return self.readStringAt(self._stream.tell())

    def readStringAt(self, offset: int) -> str:
        return self.readStringAtUntil(offset, b'\x00')

    def readStringAtUntil(self, offset: int, stopper: bytes) -> str:
        origin = self._stream.tell()
        self._stream.seek(offset, SEEK_SET)
        result = self.readUntil(stopper)
        self._stream.seek(origin, SEEK_SET)
        return result.decode("UTF-8")

def readAt(stream: BufferedReader, offset: int, func: Callable[[], Any], *arg, **kwargs) -> Any:
    origin = stream.tell()
    stream.seek(offset, SEEK_SET)
    result = func(*arg, **kwargs)
    stream.seek(origin, SEEK_SET)
    return result

@dataclass(slots=True)
class BankHeader:
    name: str
    filename: str
    mem_usage: int
    version: int

@dataclass(frozen=True)
class BankSource:
    bankPathOffset: int
    bankPath: str
    file_name: str
    file_size: int
    sample_rate: int
    volume: float
    data_offset: int
    play_action: int
    unknown_data: dict = field(default_factory=dict)

@dataclass(slots=True)
class BankEvent:
    name: str
    sources: list[BankSource] = field(init=False, default_factory=list)
    unknown_string_data_format: list[str] = field(default_factory=list)

@dataclass(slots=True)
class BankInfo:
    header: BankHeader = field(init=False)
    events: dict[str, BankEvent] = field(default_factory=dict)

@dataclass(slots=True)
class MsscmpParser:
    bankinfo: BankInfo = field(init=False, default_factory=BankInfo)
    verbose: bool = field(default=False)

    def process(self, stream: BufferedReader, dump_path: str = None):
        #! 0x42414e4b == b'BANK' | Big Endian
        #! 0x4b4e4142 == b'KNAB' | Little Endian
        signature = stream.read(4)
        if signature not in  (b'BANK', b'KNAB'):
            raise Exception("File is not a Soundbank.")

        reader = BufferedDataReader(stream, '<' if signature == b'KNAB' else '>')
        self.bankinfo.header = self.readBinkHeader(reader)

        _, event_table_start, source_table_start, *_  = reader.readInts(5) # _, event_offset, 4212, 4212, 4212
        data_end, event_count = reader.readInts(2)
        *_, source_count = reader.readInts(3)

        if (stream.tell() != event_table_start):
            stream.seek(event_table_start, SEEK_SET)

        for _ in range(event_count):
            offset_event_name, offset_event_details = reader.readInts(2)
            event_name = reader.readStringAt(offset_event_name)
            string_data_format = reader.readStringAt(offset_event_details).split(';')
            event = BankEvent(event_name, string_data_format)
            print(f"{string_data_format = }")
            if string_data_format[2] == "1": # normal event data
                source_list = string_data_format[3].split(":")
                print(event_name, [(source_name, amount_x) for source_name, amount_x in zip(source_list[0::2], source_list[1::2])])
            elif string_data_format[2] == "5": # Cached sounds ??
                root_source_name = string_data_format[3]
                source_list = string_data_format[4].split(":")
                print(event_name, root_source_name, source_list)

            self.bankinfo.events[event_name] = event

        if (stream.tell() != source_table_start):
            stream.seek(source_table_start, SEEK_SET)

        for _ in range(source_count):
            path_offset, info_offset = reader.readInts(2)
            source: BankSource = readAt(stream, info_offset, self.readEntry, reader, path_offset)

            if self.bankinfo.events.get(os.path.dirname(source.bankPath), None) is not None:
                self.bankinfo.events[os.path.dirname(source.bankPath)].sources.append(source)

            if dump_path is not None:
                self.dumpSource(stream, dump_path, source)
        
        if self.verbose:
            pprint(self.bankinfo)

    def dumpSource(self, stream: BufferedReader, dump_path: str, bankSource: BankSource):
        path = f"{dump_path}/{os.path.dirname(bankSource.bankPath)}"
        if not os.path.exists(path): os.makedirs(path)
        with open(f"{dump_path}/{bankSource.bankPath}.binka", "wb") as f:
            binka_data = readAt(stream, bankSource.data_offset, stream.read, bankSource.file_size)
            f.write(binka_data)

    def readBinkHeader(self, reader: BufferedDataReader) -> BankHeader:
        # version: Has to be 8 to match runtime
        # mem_usage: Number of bytes required to build entry data(name, file_name, file_location, file_size, ...)
        version, mem_usage, _ = reader.readInts(3)
        filename = reader.readString()
        name = reader.readStringAt(0x38)
        return BankHeader(name, filename, mem_usage, version)

    def readEntry(self, reader: BufferedDataReader, source_name_offset: int) -> BankSource:
        current_offset = reader.stream.tell()
        unknown_data = dict()
        unknown_data["info_offset"] = current_offset

        recived_source_name_offset = reader.readInt()
        if (source_name_offset != recived_source_name_offset):
            raise Exception(f"Unexpected offset difference: Expected {source_name_offset}(0x{source_name_offset:x}) got {recived_source_name_offset}(0x{recived_source_name_offset:x})")

        bankPath = reader.readStringAt(source_name_offset)
        file_name = reader.readStringAt(reader.readInt() + current_offset)
        # Minimal file buffer size allocated/alignment: 4Kb
        # Note: not tested with larger binka files
        file_size = reader.readInt()
        play_action = reader.readInt() # type(1 = play, 2 = loop)
        unknown_data["0x10"] = reader.readInt()
        sample_rate = reader.readInt()
        unknown_data["0x18"] = reader.readInt()
        unknown_data["0x1C"] = reader.readInt()
        unknown_data["0x20"] = reader.readInt()
        unknown_data["0x24"] = reader.readInt()
        unknown_data["0x28"] = reader.readInt()
        unknown_data["0x2C"] = reader.readInt()
        unknown_data["0x30"] = reader.readInt()
        volume = reader.readFloat() # distant scalar
        unknown_data["0x38"] = reader.readInt()
        data_offset = int(file_name.split('*')[-1].rsplit('.')[0]) # yes :^)

        source = BankSource(source_name_offset, bankPath, file_name, file_size, sample_rate, volume, data_offset, play_action, unknown_data)
        return source