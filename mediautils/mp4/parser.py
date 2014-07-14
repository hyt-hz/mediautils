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

    def iter_child(self, deep=False):
        for child in self.children:
            yield child
            if deep:
                for box in child.iter_child(deep=True):
                    yield box

    @property
    def end_offset(self):
        if self.size:
            return self.box_offset + self.size
        else:
            return 0

    def find_children(self, box_type, deep=False, only_first=False):
        children = []
        for child in self.iter_child(deep=deep):
            if child.type == box_type:
                if only_first:
                    return child
                else:
                    children.append(child)
        return children

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


class BoxMdhd(Box):
    boxtype = 'mdhd'

    def _parse(self, data):
        self.version, = struct.unpack('>B', data.read(1))
        self.flag = data.read(3)
        if self.version == 0:
            self.creation_time, = struct.unpack('>I', data.read(4))
            self.modification_time, = struct.unpack('>I', data.read(4))
            self.timescale, = struct.unpack('>I', data.read(4))
            self.duration, = struct.unpack('>I', data.read(4))
        else:
            self.creation_time, = struct.unpack('>Q', data.read(8))
            self.modification_time, = struct.unpack('>Q', data.read(8))
            self.timescale, = struct.unpack('>I', data.read(4))
            self.duration, = struct.unpack('>Q', data.read(8))
        data.forward(4)


class BoxMinf(Box):
    boxtype = 'minf'
    direct_children = True


class BoxStbl(Box):
    boxtype = 'stbl'
    direct_children = True


class BoxStts(Box):
    boxtype = 'stts'

    def _parse(self, data):
        self.version = data.read(1)
        self.flag = data.read(3)
        self.entry_count, = struct.unpack('>I', data.read(4))
        self._entries = data.read(self.entry_count*8)

    def iter_time_to_sample(self):
        offset = 0
        end_offset = self.entry_count*8
        while offset + 8 <= end_offset:
            yield struct.unpack('>I', self._entries[offset:offset+4])[0], struct.unpack('>I', self._entries[offset+4:offset+8])[0]
            offset += 8

    def sample_time(self, sample):
        accum_samples = 0
        accum_time = 0
        for sample_count, sample_delta in self.iter_time_to_sample():
            if sample < accum_samples + sample_count:
                return accum_time + (sample - accum_samples)*sample_delta
            accum_samples += sample_count
            accum_time += sample_count*sample_delta


class BoxStss(Box):
    # return sample starts from 0 instead of from 1
    boxtype = 'stss'

    def _parse(self, data):
        self.version = data.read(1)
        self.flag = data.read(3)
        self.entry_count, = struct.unpack('>I', data.read(4))
        self._entries = data.read(self.entry_count*4)

    def sync_sample(self, index):
        if index+1 > self.entry_count:
            raise Exception('stss index {} too large'.format(index))
        return struct.unpack('>I', self._entries[index*4:index*4+4])[0] - 1

    def iter_sync_sample(self):
        offset = 0
        end_offset = self.entry_count*4
        while offset + 4 <= end_offset:
            yield struct.unpack('>I', self._entries[offset:offset+4])[0] - 1
            offset += 4


if __name__ == '__main__':

    def print_all_children(box, prefix=''):
        for child in box.iter_child():
            print prefix, child.type
            print_all_children(child, prefix+'  ')

    with open('ted.mp4', 'rb') as f:
        data = FileCache(f)
        mp4 = BoxRoot(data)
        print_all_children(mp4)

    print '\nstss data:'
    for trak in mp4.find_children('trak', deep=True):
        stts = trak.find_children('stts', deep=True, only_first=True)
        stss = trak.find_children('stss', deep=True, only_first=True)
        mdhd = trak.find_children('mdhd', deep=True, only_first=True)
        if stts and stss:
            for sync_sample in stss.iter_sync_sample():
                print sync_sample, stts.sample_time(sync_sample), float(stts.sample_time(sync_sample))/mdhd.timescale


