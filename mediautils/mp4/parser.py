import struct
import traceback
import logging



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

        if hasattr(cls, 'boxtype'):
            cls.box_classes[cls.boxtype] = cls

        super(BoxMetaClass, cls).__init__(name, bases, dct)


class Box(object):

    box_classes = {}  # key value pair of box type name and corresponding subclass
                      # filled by metaclass
    __metaclass__ = BoxMetaClass
    direct_children = False

    def __init__(self, data, parent):
        self.box_offset = data.tell()
        self.parent = parent
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
        self.body_offset = data.tell()
        self._parse(data)

    def _parse(self, data):
        if self.direct_children:
            self._parse_child(data)
        else:
            data.seek(self.box_offset+self.size)

    def _parse_child(self, data):
        while True:
            if self.parent and self.parent.end_offset and data.tell() >= self.parent.end_offset:
                return
            if self.end_offset and data.tell() >= self.end_offset:
                return
            try:
                child = Box.factory(data, self)
            except Exception:
                print traceback.format_exc()
                return
            if child:
                self.children.append(child)
            else:
                return

    def iter(self):
        for child in self.children:
            yield child
            for box in child.iter():
                yield box

    def iter_child(self):
        for child in self.children:
            yield child

    @property
    def end_offset(self):
        if self.size:
            return self.box_offset + self.size
        else:
            return 0

    @classmethod
    def factory(cls, data, parent):
        boxtype = data.peek(8)[4:8]
        if len(boxtype) == 0:
            return None
        if boxtype in cls.box_classes:
            return cls.box_classes[boxtype](data, parent)
        else:
            return cls(data, parent)


class BoxRoot(Box):
    boxtype = 'ROOT'
    direct_children = True

    def __init__(self, data):
        self.box_offset = data.tell()
        self.body_offset = self.box_offset
        self.parent = None
        self.size = 0
        self.type = self.boxtype
        self.children = []
        self._parse(data)


class BoxMoov(Box):
    boxtype = 'moov'

    def _parse(self, data):
        self._parse_child(data)


class BoxTrak(Box):
    boxtype = 'trak'
    direct_children = True


class BoxMdia(Box):
    boxtype = 'mdia'
    direct_children = True


if __name__ == '__main__':

    def print_child(box, prefix=''):
        for child in box.iter_child():
            print prefix, child.type
            print_child(child, prefix+'  ')

    with open('ted.mp4', 'rb') as f:
        data = FileCache(f)
        mp4 = BoxRoot(data)
        print_child(mp4)

