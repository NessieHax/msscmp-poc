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
from io import SEEK_SET, BufferedIOBase, BufferedReader
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
    _stream: BufferedIOBase = field(init=True)
    _endianness: str = field(default='>') # big endian

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

def readAt(stream: BufferedIOBase, offset: int, func: Callable[[], Any], *arg, **kwargs) -> Any:
    origin = stream.tell()
    stream.seek(offset, SEEK_SET)
    result = func(*arg, **kwargs)
    stream.seek(origin, SEEK_SET)
    return result

@dataclass(slots=True)
class BankHeader:
    name: str = field(init=False)
    filename: str = field(init=False)
    mem_usage: int = field(init=False)
    version: int = field(init=False)

@dataclass(slots=True)
class BankInfo:
    header: BankHeader = field(default=BankHeader)
    soundBank: dict = field(init=False)



@dataclass(slots=True)
class MsscmpParser:
    bankinfo: BankInfo = field(init=False, default_factory=BankInfo)

    def process(self, stream: BufferedReader, dump_path: str = None, log: bool = False):
        #! 0x42414e4b == b'BANK' | Big Endian
        #! 0x4b4e4142 == b'KNAB' | Little Endian
        signature = stream.read(4)
        if signature not in  (b'BANK', b'KNAB'):
            raise Exception("File is not a Soundbank.")

        reader = BufferedDataReader(stream, '<' if signature == b'KNAB' else '>')

        self.bankinfo.header.version = reader.readInt() # has to be 8 to match runtime
        self.bankinfo.header.mem_usage = reader.readInt() # Number of bytes required to build entry data(name, file_name, file_location, file_size, ...)

        reader.readInt() # 0 ?
        self.bankinfo.header.filename = reader.readString()
        self.bankinfo.header.name = reader.readStringAt(0x38)
        self.bankinfo.soundBank = dict()

        _, table_start = reader.readInts(2)
        reader.readInts(3) # 4212, 4212, 4212
        data_end, entry_count = reader.readInts(2)

        if (stream.tell() != table_start):
            stream.seek(table_start, SEEK_SET)

        for _ in range(entry_count):
            offset_a, offset_b = reader.readInts(2)
            soundPath = reader.readStringAt(offset_a)
            self.bankinfo.soundBank[soundPath] = dict()
            self.bankinfo.soundBank[soundPath]['unknown_string_data_format'] = reader.readStringAt(offset_b).split(';')

        for _ in range(entry_count):
            offset_path, info_offset = reader.readInts(2)

            origin = stream.tell()
            stream.seek(info_offset, SEEK_SET)
            
            data = dict()
            data["info_offset"] = info_offset

            a = reader.readInt()
            if (offset_path != a):
                raise Exception(f"Unexpected offset difference: Expected {offset_path}({offset_path:x}) got {a}({a:x})", offset_path, a)

            data["bankPathOffset"] = offset_path
            data["bankPath"] = reader.readStringAt(data["bankPathOffset"])
            data["file_name"] = reader.readStringAt(reader.readInt() + info_offset)
            data["file_size"] = reader.readInt()
            data["0x0C"] = reader.readInt()
            data["0x10"] = reader.readInt()
            data["sample_rate"] = reader.readInt()
            data["0x18"] = reader.readInt()
            data["0x1C"] = reader.readInt()
            data["0x20"] = reader.readInt()
            data["0x24"] = reader.readInt()
            data["0x28"] = reader.readInt()
            data["0x2C"] = reader.readInt()
            data["0x30"] = reader.readInt()
            data["0x34"] = reader.readFloat() # volume ??
            data["0x38"] = reader.readInt()
            data["data_offset"] = int(data["file_name"].split('*')[-1].rsplit('.')[0]) # yes :^)
            self.bankinfo.soundBank[data["bankPath"]] = data

            stream.seek(origin, SEEK_SET)

            if dump_path is not None:
                lastCharIndex = data['bankPath'].rfind('/')
                if lastCharIndex == -1:
                    raise Exception()
                path = f"{dump_path}/{data['bankPath'][:lastCharIndex]}"
                if not os.path.exists(path): os.makedirs(path)
                with open(f"{dump_path}/{data['bankPath']}.binka", "wb") as f:
                    binka_data = readAt(stream, data["data_offset"], stream.read, data["file_size"])
                    f.write(binka_data)

        if log:
            pprint(self.bankinfo, sort_dicts=False)