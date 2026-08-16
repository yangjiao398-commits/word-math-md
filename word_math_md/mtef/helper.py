class Helper:
    ENDOFCHAIN = 0xFFFFFFFE
    FREESECT = 0xFFFFFFFF

    @classmethod
    def bytes2int(cls, bts):
        if bts is None:
            return None
        return int.from_bytes(bts, byteorder="little")
