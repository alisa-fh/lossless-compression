import logging
import contextlib, sys
import os
from tqdm import tqdm
MODEL_ORDER = 3

word_dict = {"a": "\\item", "b": "{\\bf", "c":"\\begin{align*}", "d":"\\begin{enumerate}", "e": "\\end{enumerate}", "f": "\\section", "g": "\\subsection", "h": "\\draw[-latex]", "i": "\\documentclass{",  "j": "\\end{center}", "k": "\\dots", "l": "function", "m": "\\usepackage{", "n": "which", "o": "\\begin{pmatrix}", "p": "\\end{align*}", "q": "\\begin{center}"}

def lz_compress(
    input_string: str, max_offset: int = 4095, max_length: int = 15
) -> [(int, int, str)]:
    """Compress the input string into a list of length, offset, char values"""
    # Create the input
    for key in word_dict:
        input_string = input_string.replace(word_dict[key], chr(7) + key)
    input_array = str(input_string[:])

    # Create a string of the characters which have been passed
    window = ""
    ## Store output in this list
    output = []
    print("Current Process: LZ-77")
    pbar = tqdm(total=len(input_string))
    while input_array != "":
        length, offset = best_length_offset(window, input_array, max_length, max_offset)
        output.append((offset, length, input_array[0]))
        window += input_array[:length]
        input_array = input_array[length:]
        pbar.update(length)
    pbar.close()
    return output


def to_bytes(
    compressed_representation: [(int, int, str)],
    offset_bits: int = 12,
    length_bits: int = 4,
) -> bytearray:
    """Turn the compression representation into a byte array"""
    output = bytearray()

    assert (
        offset_bits + length_bits
    ) % 8 == 0, f"Please provide offset_bits and length_bits which add up to a multiple of 8, so they can be efficiently packed. Received {offset_bits} and {length_bits}."
    offset_length_bytes = int((offset_bits + length_bits) / 8)

    for value in compressed_representation:
        offset, length, char = value
        assert (
            offset < 2 ** offset_bits
        ), f"Offset of {offset} is too large, only have {offset_bits} to store this value"
        assert (
            length < 2 ** length
        ), f"Length of {length} is too large, only have {length} to store this value"

        offset_length_value = (offset << length_bits) + length
        logging.debug(f"Offset: {offset}")
        logging.debug(f"Length: {length}")
        logging.debug(f"Offset and length: 0b{offset_length_value:b}")

        for count in range(offset_length_bytes):
            output.append(
                (offset_length_value >> (8 * (offset_length_bytes - count - 1)))
                & (0b11111111)
            )
        if char is not None:
            if offset == 4095:
                output.append(ord(char))
        else:
            output.append(0)


    return output

def best_length_offset(
    window: str, input_string: str, max_length: int = 15,  max_offset: int = 4095
) -> (int, int):
    """Take the window and an input string and return the offset and length
    with the biggest length of the input string as a substring"""

    if max_offset < len(window):
        cut_window = window[0:max_offset]
    else:
        cut_window = window

    # Return (0, 0) if the string provided is empty
    if input_string is None or input_string == "":
        return (0, 4095)

    # Initialise result parameters - best case so far
    length, offset = (1, 4095)

    # This should also catch the empty window case
    # If not seen before
    if input_string[0] not in cut_window:
        best_length = repeating_length_from_start(input_string[0], input_string[1:])
        return (min((length + best_length), max_length), offset)

    # Best length now zero to allow occurences to take priority
    length = 0

    # Test for every string in the window, in reverse order to keep the offset as low as possible
    # Look for either the whole window or up to max offset away, whichever is smaller
    for index in range(0, (len(cut_window) )):
        # Get the character at this offset
        char = cut_window[index]
        if char == input_string[0]:
            found_offset = index
            # Collect any further strings which can be found
            found_length = repeating_length_from_start(
                cut_window[index:], input_string
            )
            if found_length > length:
                length = found_length
                offset = found_offset

    # Only return up to the maximum length
    # This will capture the maximum number of characters allowed
    # although it might not capture the maximum amount of characters *possible*
    return (min(length, max_length), offset)


def repeating_length_from_start(window: str, input_string: str) -> int:
    """Get the maximum repeating length of the input from the start of the window"""
    if window == "" or input_string == "":
        return 0

    if window[0] == input_string[0]:
        return 1 + repeating_length_from_start(
            window[1:] + input_string[0], input_string[1:]
        )
    else:
        return 0

# ARITHMETIC:

def adaptiveArithmeticCompress(inp, bitout, offset_bits, length_bits):
    compressed_bytes = inp
    initfreqs = FlatFrequencyTable(65537)
    freqs = SimpleFrequencyTable(initfreqs)
    enc = ArithmeticEncoder(32, bitout)
    offset_length_bytes = int((offset_bits + length_bits) / 8)
    print("Current Process: Adaptive Arithmetic Compress")
    pbar = tqdm(total=len(compressed_bytes))
    while len(compressed_bytes) > 0:
        offset_length_value = 0
        for x in range(offset_length_bytes):
            offset_length_value = (offset_length_value * 256) + int(
                compressed_bytes.pop(0)
            )
            pbar.update(1)

        offset = offset_length_value >> length_bits
        # Read and encode one byte
        enc.write(freqs, offset_length_value)
        freqs.increment(offset_length_value)
        if offset != 4095:
            continue
        else:
            char = compressed_bytes.pop(0)
        enc.write(freqs, char)
        freqs.increment(char)
        pbar.update(1)
    enc.write(freqs, 65536)  # EOF
    enc.finish()  # Flush remaining code bits


def ppmCompress(input_file, bitout, offset_bits, length_bits):
    # Set up encoder and model. In this PPM model, symbol 256 represents EOF;
    # its frequency is 1 in the order -1 context but its frequency
    # is 0 in all other contexts (which have non-negative order).
    enc = ArithmeticEncoder(32, bitout)
    model = PpmModel(MODEL_ORDER, 257, 256)
    history = []

    while True:
        # Read and encode one byte
        symbol = input_file.read(1)
        if len(symbol) == 0:
            break
        symbol = symbol[0]
        encode_symbol(model, history, symbol, enc)
        model.increment_contexts(history, symbol)

        if model.model_order >= 1:
            # Prepend current symbol, dropping oldest symbol if necessary
            if len(history) == model.model_order:
                history.pop()
            history.insert(0, symbol)

    encode_symbol(model, history, 256, enc)  # EOF
    enc.finish()  # Flush remaining code bits


def encode_symbol(model, history, symbol, enc):
    # Try to use highest order context that exists based on the history suffix, such
    # that the next symbol has non-zero frequency. When symbol 256 is produced at a context
    # at any non-negative order, it means "escape to the next lower order with non-empty
    # context". When symbol 256 is produced at the order -1 context, it means "EOF".
    for order in reversed(range(len(history) + 1)):
        ctx = model.root_context
        for sym in history[: order]:
            assert ctx.subcontexts is not None
            ctx = ctx.subcontexts[sym]
            if ctx is None:
                break
        else:  # ctx is not None
            if symbol != 256 and ctx.frequencies.get(symbol) > 0:
                enc.write(ctx.frequencies, symbol)
                return
            # Else write context escape symbol and continue decrementing the order
            enc.write(ctx.frequencies, 256)
    # Logic for order = -1
    enc.write(model.order_minus1_freqs, symbol)

#MAIN FUNCTION
def compress_file(input_file: str):
    """Open and read an input file, compress it, and write the compressed
    values to the output file"""
    try:
        with open(input_file) as f:
            input_array = f.read()
    except FileNotFoundError:
        print(f"Could not find input file at: {input_file}")
        raise
    except Exception:
        raise

    arith_output_file = input_file[:-4] + "2.lz"
    output_file = input_file[:-4] + ".lz"

    lz_compressed = lz_compress(input_array)
    lz_bytes = to_bytes(lz_compressed)

    with contextlib.closing(BitOutputStream(open(arith_output_file, "wb"))) as a_output:
        adaptiveArithmeticCompress(lz_bytes, a_output, 12, 4)
    with open(input_file, "rb") as p_inp, \
            contextlib.closing(BitOutputStream(open(output_file, "wb"))) as p_output:
        ppmCompress(p_inp, p_output, 12, 4)

    arith_result_size = os.stat(arith_output_file).st_size
    ppm_result_size = os.stat(output_file).st_size
    if arith_result_size > ppm_result_size:
        os.remove(arith_output_file)
        with open(output_file, 'rb') as f:
            with open('intermediate.txt', 'wb') as f2:
                f2.write(str('0').encode('ascii')) #flag for ppm
                f2.write(f.read())
        os.rename('intermediate.txt', output_file)
    else:
        os.remove(output_file)
        os.rename(arith_output_file, arith_output_file[:-4] + ".lz")
        with open(output_file, 'rb') as f:
            with open('intermediate.lz', 'wb') as f2:
                f2.write(str('1').encode('ascii')) #flag for arithmetic
                f2.write(f.read())
        os.rename('intermediate.lz', output_file)

################## BASE CODE ####################
#
# Reference arithmetic coding
# Copyright (c) Project Nayuki
#
# https://www.nayuki.io/page/reference-arithmetic-coding
# https://github.com/nayuki/Reference-arithmetic-coding
#


# ---- Arithmetic coding core classes ----

# Provides the state and behaviors that arithmetic coding encoders and decoders share.
class ArithmeticCoderBase:

    # Constructs an arithmetic coder, which initializes the code range.
    def __init__(self, numbits):
        if numbits < 1:
            raise ValueError("State size out of range")

        # -- Configuration fields --
        # Number of bits for the 'low' and 'high' state variables. Must be at least 1.
        # - Larger values are generally better - they allow a larger maximum frequency total (maximum_total),
        #   and they reduce the approximation error inherent in adapting fractions to integers;
        #   both effects reduce the data encoding loss and asymptotically approach the efficiency
        #   of arithmetic coding using exact fractions.
        # - But larger state sizes increase the computation time for integer arithmetic,
        #   and compression gains beyond ~30 bits essentially zero in real-world applications.
        # - Python has native bigint arithmetic, so there is no upper limit to the state size.
        #   For Java and C++ where using native machine-sized integers makes the most sense,
        #   they have a recommended value of num_state_bits=32 as the most versatile setting.
        self.num_state_bits = numbits
        # Maximum range (high+1-low) during coding (trivial), which is 2^num_state_bits = 1000...000.
        self.full_range = 1 << self.num_state_bits
        # The top bit at width num_state_bits, which is 0100...000.
        self.half_range = self.full_range >> 1  # Non-zero
        # The second highest bit at width num_state_bits, which is 0010...000. This is zero when num_state_bits=1.
        self.quarter_range = self.half_range >> 1  # Can be zero
        # Minimum range (high+1-low) during coding (non-trivial), which is 0010...010.
        self.minimum_range = self.quarter_range + 2  # At least 2
        # Maximum allowed total from a frequency table at all times during coding. This differs from Java
        # and C++ because Python's native bigint avoids constraining the size of intermediate computations.
        self.maximum_total = self.minimum_range
        # Bit mask of num_state_bits ones, which is 0111...111.
        self.state_mask = self.full_range - 1

        # -- State fields --
        # Low end of this arithmetic coder's current range. Conceptually has an infinite number of trailing 0s.
        self.low = 0
        # High end of this arithmetic coder's current range. Conceptually has an infinite number of trailing 1s.
        self.high = self.state_mask

    # Updates the code range (low and high) of this arithmetic coder as a result
    # of processing the given symbol with the given frequency table.
    # Invariants that are true before and after encoding/decoding each symbol
    # (letting full_range = 2^num_state_bits):
    # - 0 <= low <= code <= high < full_range. ('code' exists only in the decoder.)
    #   Therefore these variables are unsigned integers of num_state_bits bits.
    # - low < 1/2 * full_range <= high.
    #   In other words, they are in different halves of the full range.
    # - (low < 1/4 * full_range) || (high >= 3/4 * full_range).
    #   In other words, they are not both in the middle two quarters.
    # - Let range = high - low + 1, then full_range/4 < minimum_range
    #   <= range <= full_range. These invariants for 'range' essentially
    #   dictate the maximum total that the incoming frequency table can have.
    def update(self, freqs, symbol):
        # State check
        low = self.low
        high = self.high
        if low >= high or (low & self.state_mask) != low or (high & self.state_mask) != high:
            raise AssertionError("Low or high out of range")
        range = high - low + 1
        if not (self.minimum_range <= range <= self.full_range):
            raise AssertionError("Range out of range")

        # Frequency table values check
        total = freqs.get_total()
        symlow = freqs.get_low(symbol)
        symhigh = freqs.get_high(symbol)
        if symlow == symhigh:
            raise ValueError("Symbol has zero frequency")
        if total > self.maximum_total:
            raise ValueError("Cannot code symbol because total is too large")

        # Update range
        newlow = low + symlow * range // total
        newhigh = low + symhigh * range // total - 1
        self.low = newlow
        self.high = newhigh

        # While low and high have the same top bit value, shift them out
        while ((self.low ^ self.high) & self.half_range) == 0:
            self.shift()
            self.low = ((self.low << 1) & self.state_mask)
            self.high = ((self.high << 1) & self.state_mask) | 1
        # Now low's top bit must be 0 and high's top bit must be 1

        # While low's top two bits are 01 and high's are 10, delete the second highest bit of both
        while (self.low & ~self.high & self.quarter_range) != 0:
            self.underflow()
            self.low = (self.low << 1) ^ self.half_range
            self.high = ((self.high ^ self.half_range) << 1) | self.half_range | 1

    # Called to handle the situation when the top bit of 'low' and 'high' are equal.
    def shift(self):
        raise NotImplementedError()

    # Called to handle the situation when low=01(...) and high=10(...).
    def underflow(self):
        raise NotImplementedError()


# Encodes symbols and writes to an arithmetic-coded bit stream.
class ArithmeticEncoder(ArithmeticCoderBase):

    # Constructs an arithmetic coding encoder based on the given bit output stream.
    def __init__(self, numbits, bitout):
        super(ArithmeticEncoder, self).__init__(numbits)
        # The underlying bit output stream.
        self.output = bitout
        # Number of saved underflow bits. This value can grow without bound.
        self.num_underflow = 0

    # Encodes the given symbol based on the given frequency table.
    # This updates this arithmetic coder's state and may write out some bits.
    def write(self, freqs, symbol):
        if not isinstance(freqs, CheckedFrequencyTable):
            freqs = CheckedFrequencyTable(freqs)
        self.update(freqs, symbol)

    # Terminates the arithmetic coding by flushing any buffered bits, so that the output can be decoded properly.
    # It is important that this method must be called at the end of the each encoding process.
    # Note that this method merely writes data to the underlying output stream but does not close it.
    def finish(self):
        self.output.write(1)

    def shift(self):
        bit = self.low >> (self.num_state_bits - 1)
        self.output.write(bit)

        # Write out the saved underflow bits
        for _ in range(self.num_underflow):
            self.output.write(bit ^ 1)
        self.num_underflow = 0

    def underflow(self):
        self.num_underflow += 1


# Reads from an arithmetic-coded bit stream and decodes symbols.
class ArithmeticDecoder(ArithmeticCoderBase):

    # Constructs an arithmetic coding decoder based on the
    # given bit input stream, and fills the code bits.
    def __init__(self, numbits, bitin):
        super(ArithmeticDecoder, self).__init__(numbits)
        # The underlying bit input stream.
        self.input = bitin
        # The current raw code bits being buffered, which is always in the range [low, high].
        self.code = 0
        for _ in range(self.num_state_bits):
            self.code = self.code << 1 | self.read_code_bit()

    # Decodes the next symbol based on the given frequency table and returns it.
    # Also updates this arithmetic coder's state and may read in some bits.
    def read(self, freqs):
        if not isinstance(freqs, CheckedFrequencyTable):
            freqs = CheckedFrequencyTable(freqs)

        # Translate from coding range scale to frequency table scale
        total = freqs.get_total()
        if total > self.maximum_total:
            raise ValueError("Cannot decode symbol because total is too large")
        range = self.high - self.low + 1
        offset = self.code - self.low
        value = ((offset + 1) * total - 1) // range
        assert value * range // total <= offset
        assert 0 <= value < total

        # A kind of binary search. Find highest symbol such that freqs.get_low(symbol) <= value.
        start = 0
        end = freqs.get_symbol_limit()
        while end - start > 1:
            middle = (start + end) >> 1
            if freqs.get_low(middle) > value:
                end = middle
            else:
                start = middle
        assert start + 1 == end

        symbol = start
        assert freqs.get_low(symbol) * range // total <= offset < freqs.get_high(symbol) * range // total
        self.update(freqs, symbol)
        if not (self.low <= self.code <= self.high):
            raise AssertionError("Code out of range")
        return symbol

    def shift(self):
        self.code = ((self.code << 1) & self.state_mask) | self.read_code_bit()

    def underflow(self):
        self.code = (self.code & self.half_range) | ((self.code << 1) & (self.state_mask >> 1)) | self.read_code_bit()

    # Returns the next bit (0 or 1) from the input stream. The end
    # of stream is treated as an infinite number of trailing zeros.
    def read_code_bit(self):
        temp = self.input.read()
        if temp == -1:
            temp = 0
        return temp


# ---- Frequency table classes ----

# A table of symbol frequencies. The table holds data for symbols numbered from 0
# to get_symbol_limit()-1. Each symbol has a frequency, which is a non-negative integer.
# Frequency table objects are primarily used for getting cumulative symbol
# frequencies. These objects can be mutable depending on the implementation.
class FrequencyTable:

    # Returns the number of symbols in this frequency table, which is a positive number.
    def get_symbol_limit(self):
        raise NotImplementedError()

    # Returns the frequency of the given symbol. The returned value is at least 0.
    def get(self, symbol):
        raise NotImplementedError()

    # Sets the frequency of the given symbol to the given value.
    # The frequency value must be at least 0.
    def set(self, symbol, freq):
        raise NotImplementedError()

    # Increments the frequency of the given symbol.
    def increment(self, symbol):
        raise NotImplementedError()

    # Returns the total of all symbol frequencies. The returned value is at
    # least 0 and is always equal to get_high(get_symbol_limit() - 1).
    def get_total(self):
        raise NotImplementedError()

    # Returns the sum of the frequencies of all the symbols strictly
    # below the given symbol value. The returned value is at least 0.
    def get_low(self, symbol):
        raise NotImplementedError()

    # Returns the sum of the frequencies of the given symbol
    # and all the symbols below. The returned value is at least 0.
    def get_high(self, symbol):
        raise NotImplementedError()


# An immutable frequency table where every symbol has the same frequency of 1.
# Useful as a fallback model when no statistics are available.
class FlatFrequencyTable(FrequencyTable):

    # Constructs a flat frequency table with the given number of symbols.
    def __init__(self, numsyms):
        if numsyms < 1:
            raise ValueError("Number of symbols must be positive")
        self.numsymbols = numsyms  # Total number of symbols, which is at least 1

    # Returns the number of symbols in this table, which is at least 1.
    def get_symbol_limit(self):
        return self.numsymbols

    # Returns the frequency of the given symbol, which is always 1.
    def get(self, symbol):
        self._check_symbol(symbol)
        return 1

    # Returns the total of all symbol frequencies, which is
    # always equal to the number of symbols in this table.
    def get_total(self):
        return self.numsymbols

    # Returns the sum of the frequencies of all the symbols strictly below
    # the given symbol value. The returned value is equal to 'symbol'.
    def get_low(self, symbol):
        self._check_symbol(symbol)
        return symbol

    # Returns the sum of the frequencies of the given symbol and all
    # the symbols below. The returned value is equal to 'symbol' + 1.
    def get_high(self, symbol):
        self._check_symbol(symbol)
        return symbol + 1

    # Returns silently if 0 <= symbol < numsymbols, otherwise raises an exception.
    def _check_symbol(self, symbol):
        if 0 <= symbol < self.numsymbols:
            return
        else:
            raise ValueError("Symbol out of range")

    # Returns a string representation of this frequency table. The format is subject to change.
    def __str__(self):
        return "FlatFrequencyTable={}".format(self.numsymbols)

    # Unsupported operation, because this frequency table is immutable.
    def set(self, symbol, freq):
        raise NotImplementedError()

    # Unsupported operation, because this frequency table is immutable.
    def increment(self, symbol):
        raise NotImplementedError()


# A mutable table of symbol frequencies. The number of symbols cannot be changed
# after construction. The current algorithm for calculating cumulative frequencies
# takes linear time, but there exist faster algorithms such as Fenwick trees.
class SimpleFrequencyTable(FrequencyTable):

    # Constructs a simple frequency table in one of two ways:
    # - SimpleFrequencyTable(sequence):
    #   Builds a frequency table from the given sequence of symbol frequencies.
    #   There must be at least 1 symbol, and no symbol has a negative frequency.
    # - SimpleFrequencyTable(freqtable):
    #   Builds a frequency table by copying the given frequency table.
    def __init__(self, freqs):
        if isinstance(freqs, FrequencyTable):
            numsym = freqs.get_symbol_limit()
            self.frequencies = [freqs.get(i) for i in range(numsym)]
        else:  # Assume it is a sequence type
            self.frequencies = list(freqs)  # Make copy

        # 'frequencies' is a list of the frequency for each symbol.
        # Its length is at least 1, and each element is non-negative.
        if len(self.frequencies) < 1:
            raise ValueError("At least 1 symbol needed")
        for freq in self.frequencies:
            if freq < 0:
                raise ValueError("Negative frequency")

        # Always equal to the sum of 'frequencies'
        self.total = sum(self.frequencies)

        # cumulative[i] is the sum of 'frequencies' from 0 (inclusive) to i (exclusive).
        # Initialized lazily. When it is not None, the data is valid.
        self.cumulative = None

    # Returns the number of symbols in this frequency table, which is at least 1.
    def get_symbol_limit(self):
        return len(self.frequencies)

    # Returns the frequency of the given symbol. The returned value is at least 0.
    def get(self, symbol):
        self._check_symbol(symbol)
        return self.frequencies[symbol]

    # Sets the frequency of the given symbol to the given value. The frequency value
    # must be at least 0. If an exception is raised, then the state is left unchanged.
    def set(self, symbol, freq):
        self._check_symbol(symbol)
        if freq < 0:
            raise ValueError("Negative frequency")
        temp = self.total - self.frequencies[symbol]
        assert temp >= 0
        self.total = temp + freq
        self.frequencies[symbol] = freq
        self.cumulative = None

    # Increments the frequency of the given symbol.
    def increment(self, symbol):
        self._check_symbol(symbol)
        self.total += 1
        self.frequencies[symbol] += 1
        self.cumulative = None

    # Returns the total of all symbol frequencies. The returned value is at
    # least 0 and is always equal to get_high(get_symbol_limit() - 1).
    def get_total(self):
        return self.total

    # Returns the sum of the frequencies of all the symbols strictly
    # below the given symbol value. The returned value is at least 0.
    def get_low(self, symbol):
        self._check_symbol(symbol)
        if self.cumulative is None:
            self._init_cumulative()
        return self.cumulative[symbol]

    # Returns the sum of the frequencies of the given symbol
    # and all the symbols below. The returned value is at least 0.
    def get_high(self, symbol):
        self._check_symbol(symbol)
        if self.cumulative is None:
            self._init_cumulative()
        return self.cumulative[symbol + 1]

    # Recomputes the array of cumulative symbol frequencies.
    def _init_cumulative(self):
        cumul = [0]
        sum = 0
        for freq in self.frequencies:
            sum += freq
            cumul.append(sum)
        assert sum == self.total
        self.cumulative = cumul

    # Returns silently if 0 <= symbol < len(frequencies), otherwise raises an exception.
    def _check_symbol(self, symbol):
        if 0 <= symbol < len(self.frequencies):
            return
        else:
            raise ValueError("Symbol out of range")

    # Returns a string representation of this frequency table,
    # useful for debugging only, and the format is subject to change.
    def __str__(self):
        result = ""
        for (i, freq) in enumerate(self.frequencies):
            result += "{}\t{}\n".format(i, freq)
        return result


# A wrapper that checks the preconditions (arguments) and postconditions (return value) of all
# the frequency table methods. Useful for finding faults in a frequency table implementation.
class CheckedFrequencyTable(FrequencyTable):

    def __init__(self, freqtab):
        # The underlying frequency table that holds the data
        self.freqtable = freqtab

    def get_symbol_limit(self):
        result = self.freqtable.get_symbol_limit()
        if result <= 0:
            raise AssertionError("Non-positive symbol limit")
        return result

    def get(self, symbol):
        result = self.freqtable.get(symbol)
        if not self._is_symbol_in_range(symbol):
            raise AssertionError("ValueError expected")
        if result < 0:
            raise AssertionError("Negative symbol frequency")
        return result

    def get_total(self):
        result = self.freqtable.get_total()
        if result < 0:
            raise AssertionError("Negative total frequency")
        return result

    def get_low(self, symbol):
        if self._is_symbol_in_range(symbol):
            low = self.freqtable.get_low(symbol)
            high = self.freqtable.get_high(symbol)
            if not (0 <= low <= high <= self.freqtable.get_total()):
                raise AssertionError("Symbol low cumulative frequency out of range")
            return low
        else:
            self.freqtable.get_low(symbol)
            raise AssertionError("ValueError expected")

    def get_high(self, symbol):
        if self._is_symbol_in_range(symbol):
            low = self.freqtable.get_low(symbol)
            high = self.freqtable.get_high(symbol)
            if not (0 <= low <= high <= self.freqtable.get_total()):
                raise AssertionError("Symbol high cumulative frequency out of range")
            return high
        else:
            self.freqtable.get_high(symbol)
            raise AssertionError("ValueError expected")

    def __str__(self):
        return "CheckedFrequencyTable (" + str(self.freqtable) + ")"

    def set(self, symbol, freq):
        self.freqtable.set(symbol, freq)
        if not self._is_symbol_in_range(symbol) or freq < 0:
            raise AssertionError("ValueError expected")

    def increment(self, symbol):
        self.freqtable.increment(symbol)
        if not self._is_symbol_in_range(symbol):
            raise AssertionError("ValueError expected")

    def _is_symbol_in_range(self, symbol):
        return 0 <= symbol < self.get_symbol_limit()


# ---- Bit-oriented I/O streams ----

# A stream of bits that can be read. Because they come from an underlying byte stream,
# the total number of bits is always a multiple of 8. The bits are read in big endian.
class BitInputStream:

    # Constructs a bit input stream based on the given byte input stream.
    def __init__(self, inp):
        # The underlying byte stream to read from
        self.input = inp
        # Either in the range [0x00, 0xFF] if bits are available, or -1 if end of stream is reached
        self.currentbyte = 0
        # Number of remaining bits in the current byte, always between 0 and 7 (inclusive)
        self.numbitsremaining = 0

    # Reads a bit from this stream. Returns 0 or 1 if a bit is available, or -1 if
    # the end of stream is reached. The end of stream always occurs on a byte boundary.
    def read(self):
        if self.currentbyte == -1:
            return -1
        if self.numbitsremaining == 0:
            temp = self.input.read(1)
            if len(temp) == 0:
                self.currentbyte = -1
                return -1
            self.currentbyte = temp[0]
            self.numbitsremaining = 8
        assert self.numbitsremaining > 0
        self.numbitsremaining -= 1
        return (self.currentbyte >> self.numbitsremaining) & 1

    # Reads a bit from this stream. Returns 0 or 1 if a bit is available, or raises an EOFError
    # if the end of stream is reached. The end of stream always occurs on a byte boundary.
    def read_no_eof(self):
        result = self.read()
        if result != -1:
            return result
        else:
            raise EOFError()

    # Closes this stream and the underlying input stream.
    def close(self):
        self.input.close()
        self.currentbyte = -1
        self.numbitsremaining = 0


# A stream where bits can be written to. Because they are written to an underlying
# byte stream, the end of the stream is padded with 0's up to a multiple of 8 bits.
# The bits are written in big endian.
class BitOutputStream:

    # Constructs a bit output stream based on the given byte output stream.
    def __init__(self, out):
        self.output = out  # The underlying byte stream to write to
        self.currentbyte = 0  # The accumulated bits for the current byte, always in the range [0x00, 0xFF]
        self.numbitsfilled = 0  # Number of accumulated bits in the current byte, always between 0 and 7 (inclusive)

    # Writes a bit to the stream. The given bit must be 0 or 1.
    def write(self, b):
        if b not in (0, 1):
            raise ValueError("Argument must be 0 or 1")
        self.currentbyte = (self.currentbyte << 1) | b
        self.numbitsfilled += 1
        if self.numbitsfilled == 8:
            towrite = bytes((self.currentbyte,))
            self.output.write(towrite)
            self.currentbyte = 0
            self.numbitsfilled = 0

    # Closes this stream and the underlying output stream. If called when this
    # bit stream is not at a byte boundary, then the minimum number of "0" bits
    # (between 0 and 7 of them) are written as padding to reach the next byte boundary.
    def close(self):
        while self.numbitsfilled != 0:
            self.write(0)
        self.output.close()


class PpmModel:

    def __init__(self, order, symbollimit, escapesymbol):
        if order < -1 or symbollimit <= 0 or not (0 <= escapesymbol < symbollimit):
            raise ValueError()
        self.model_order = order
        self.symbol_limit = symbollimit
        self.escape_symbol = escapesymbol

        if order >= 0:
            self.root_context = PpmModel.Context(symbollimit, order >= 1)
            self.root_context.frequencies.increment(escapesymbol)
        else:
            self.root_context = None
        self.order_minus1_freqs = FlatFrequencyTable(symbollimit)

    def increment_contexts(self, history, symbol):
        if self.model_order == -1:
            return
        if len(history) > self.model_order or not (0 <= symbol < self.symbol_limit):
            raise ValueError()

        ctx = self.root_context
        ctx.frequencies.increment(symbol)
        for (i, sym) in enumerate(history):
            subctxs = ctx.subcontexts
            assert subctxs is not None

            if subctxs[sym] is None:
                subctxs[sym] = PpmModel.Context(self.symbol_limit, i + 1 < self.model_order)
                subctxs[sym].frequencies.increment(self.escape_symbol)
            ctx = subctxs[sym]
            ctx.frequencies.increment(symbol)

    # Helper structure
    class Context:

        def __init__(self, symbols, hassubctx):
            self.frequencies = SimpleFrequencyTable([0] * symbols)
            self.subcontexts = ([None] * symbols) if hassubctx else None


def main(args):
    # Handle command line arguments
    if len(args) != 1:
        sys.exit("Usage: python encoder.py inputfile.tex")
    input_file = args[0]
    compress_file(input_file)

# Main launcher
if __name__ == "__main__":
    main(sys.argv[1:])