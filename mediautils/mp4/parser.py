import struct
import traceback


class FileCache(object):
    def __init__(self, file_obj, cache_size=0x0FFF):
        self._file = file_obj
        self._cache = None
        self._cache_read_size = cache_size
        self._cache_offset = 0
        self.offset = 0

    def read_from(self, start_offset, size, move=True):
        if self._cache is None \
                or start_offset >= self._cache_offset + self._cache_size \
                or start_offset < self._cache_offset:
            self._read2cache(start_offset)
        if self._cache_size == 0:
            return ''
        if start_offset + size <= self._cache_offset + self._cache_size:
            if move:
                self.offset = start_offset + size
            return self._cache[(start_offset-self._cache_offset):(start_offset+size-self._cache_offset)]
        else:
            data = self._cache[(start_offset-self._cache_offset):]
            self._read2cache()
            if self._cache_size == 0:
                return ''
            while True:
                if start_offset + size <= self._cache_offset + self._cache_size:
                    if move:
                        self.offset = start_offset + size
                    return data + self._cache[(start_offset-self._cache_offset):(start_offset+size-self._cache_offset)]
                else:
                    data += self._cache[(start_offset-self._cache_offset):]
                    self._read2cache()
                    if self._cache_size == 0:
                        return data

    def read(self, size):
        return self.read_from(self.offset, size)

    def peek(self, size):
        return self.read_from(self.offset, size, move=False)

    def seek(self, offset):
        self._file.seek(offset)
        self.offset = offset

    def tell(self):
        return self.offset

    def forward(self, size):
        self.offset += size

    def backward(self, size):
        if self.offset <= size:
            self.offset = 0
        else:
            self.offset -= size

    def _read2cache(self, offset=None):
        if offset is None:
            # continue
            self._cache_offset += self._cache_size
            self._cache = self._file.read(self._cache_read_size)
        else:
            self._file.seek(offset)
            self._cache = self._file.read(self._cache_read_size)
            self._cache_offset = offset

    @property
    def _cache_size(self):
        if self._cache:
            return len(self._cache)
        return 0


class BoxMetaClass(type):
    def __init__(cls, name, bases, dct):

        if hasattr(dct, 'boxtype'):
            cls.box_classes[cls.boxtype] = cls

        super(BoxMetaClass, cls).__init__(name, bases, dct)


class Box(object):

    box_classes = {}  # key value pair of box type name and corresponding subclass
                      # filled by metaclass
    __metaclass__ = BoxMetaClass

    def __init__(self, data, parent, end):
        self._box_offset = data.tell()
        self.parent = parent
        self.end = end
        self.size, = struct.unpack('>I', data.read(4))
        self.type = data.read(4)
        self.next = None
        self.children = []
        if self.size == 1:
            # 64-bit size
            self.size, = struct.unpack('>Q', data.read(8))
        elif self.size == 0:
            # to the end of file
            pass
        else:
            pass
        self._body_offset = data.tell()
        self._parse(data)

        # next box
        if self.size == 0:
            return
        elif not end or self._box_offset + self.size < end:
            try:
                data.seek(self._box_offset + self.size)
                self.next = Box.factory(data, parent, end)
            except Exception:
                print 'Failed to parse the following BOX of box {}'.format(self.type), traceback.format_exc()

    def _parse(self, data):
        pass

    def iter(self):
        yield self
        for child in self.children:
            for box in self.child.iter():
                yield box
        if self.next:
            for box in self.next.iter():
                yield box

    @classmethod
    def factory(cls, data, parent, end):
        boxtype = data.peek(8)[4:8]
        if len(boxtype) == 0:
            return None
        if boxtype in cls.box_classes:
            return cls.box_classes[boxtype](data, parent, end)
        else:
            return cls(data, parent, end)


class BoxMoov(Box):
    boxtype = 'moov'

    def _parse(self, data):
        self.version, = struct.unpack('>B', self.body[0:1])
        # 3 byte flag


class BoxTrak(Box):
    boxtype = 'trak'



if __name__ == '__main__':
    with open('ted.mp4', 'rb') as f:
        data = FileCache(f)
        mp4 = Box.factory(data, None, None)
        for box in mp4.iter():
            print box.type

