from re import I
from liteeth.common import *

# pyright: reportOperatorIssue=false
# pyright: reportAttributeAccessIssue=false

class PDM(Module):
    def __init__(self, clk_pad, data):
        self.clk_pad = clk_pad
        self.source = stream.Endpoint([("data", 32)])

        count = Signal(4) # ranges from 0 to 15
        packet_id = Signal(32)

        data_reg = Signal(24) 

        # add packet id as header
        statement = If((count & 15) == 0,
                       self.source.data.eq(packet_id),
                       self.source.valid.eq(1),
                       self.source.first.eq(1))

        # read the data in after waiting until shortly after the clock rising or falling edge
        self.sync += If((count & 7) == 5, data_reg.eq(data))

        # pulse the clock at 0 and 8
        self.comb += self.clk_pad.eq(count[-1])

        # clock out data at time at 1 and 9
        statement = statement.Elif((count & 7) == 1,
                                   self.source.data.eq(data_reg),
                                   self.source.valid.eq(1),
                                   self.source.first.eq(0))
        self.sync += statement.Else(self.source.valid.eq(0), self.source.first.eq(0))

        # set last
        self.sync += If((count & 15) == 9,
                                   self.source.last.eq(1)).Else(self.source.last.eq(0))


        # increment count and packet id
        self.sync += count.eq(count + 1)
        self.sync += If((count & 15) == 15, packet_id.eq(packet_id + 1))


class UDPStreamer(Module):
    def __init__(self, ip_address, udp_port, data_width=32, fifo_depth=8192):
        self.sink   = sink   = stream.Endpoint(eth_tty_tx_description(data_width))
        self.source = source = stream.Endpoint(eth_udp_user_description(data_width))

        ip_address = convert_ip(ip_address)

        max_packet = 96 # e.g., [packet_id, half0_word, half1_word] repeated 96 times
        packet_counter = Signal(max=max_packet+1)

        self.submodules.fifo = fifo = stream.SyncFIFO([("data", data_width)], fifo_depth, buffered=True)
        self.comb += sink.connect(fifo.sink)

        self.submodules.fsm = fsm = FSM(reset_state="IDLE")
        fsm.act("IDLE",
            If((fifo.level > 512),
                NextState("SEND"),
            )
        )
        fsm.act("SEND",
            source.valid.eq(1),
            source.last.eq((packet_counter == max_packet - 1) & fifo.source.last),
            source.src_port.eq(udp_port),
            source.dst_port.eq(udp_port),
            source.ip_address.eq(ip_address),
            source.length.eq(3 * 4 * max_packet),
            source.data.eq(fifo.source.data),
            source.last_be.eq({32:0b1000, 8:0b1}[data_width]),
            If(source.ready,
                fifo.source.ready.eq(1),
                If(fifo.source.last,
                    If(packet_counter == max_packet - 1,
                       NextState("IDLE"),
                       NextValue(packet_counter, 0)
                    ).Else(
                        NextValue(packet_counter, packet_counter + 1)
                    )
                )
            )
        )


class UDPFake500Mbps(Module):
    def __init__(self, data_width=32, clk_freq=int(50e6)):
        # Generates continuous 12-byte groups: [packet_id, word0, word1]
        # first asserted on packet_id, last asserted on word1.
        # Average payload rate ~500 Mbps at clk_freq=50 MHz.
        # Stream interface matches UDPStreamer.sink layout.
        assert data_width in (8, 32)
        self.source = source = stream.Endpoint(eth_tty_tx_description(data_width))

        # Rate control: target_words_per_cycle = 500e6 / (data_width * clk_freq)
        # For data_width=32 and clk=50e6 => 0.3125 = 5/16 words/cycle.
        # Implement fractional accumulator with numerator/denominator = 5/16.
        numerator   = 5
        denominator = 16

        acc       = Signal(max=denominator)  # 0..15
        pending   = Signal()                 # pending word to send (valid must stay high until accepted)

        packet_id       = Signal(32)
        payload_counter = Signal(32)
        word_index      = Signal(2)  # 0: header, 1: word0, 2: word1

        emit_strobe = Signal()

        # Fractional accumulator to generate average emission rate.
        self.sync += [
            If(acc + numerator >= denominator,
                acc.eq(acc + numerator - denominator),
                emit_strobe.eq(1)
            ).Else(
                acc.eq(acc + numerator),
                emit_strobe.eq(0)
            )
        ]

        # Manage pending/handshake.
        sent = Signal()
        self.comb += [
            sent.eq(source.valid & source.ready)
        ]
        self.sync += [
            If(sent,
                pending.eq(0)
            ).Elif(emit_strobe,
                pending.eq(1)
            )
        ]

        # Drive stream signals.
        self.comb += [
            source.valid.eq(pending),
            source.first.eq(word_index == 0),
            source.last.eq(word_index == 2)
        ]

        # Data mux per word within the 12-byte group.
        with_payload0 = Signal(data_width)
        with_payload1 = Signal(data_width)

        # Payload generation (simple incrementing pattern)
        self.comb += [
            with_payload0.eq(payload_counter[:data_width]),
            with_payload1.eq((payload_counter + 1)[:data_width])
        ]

        self.comb += [
            If(word_index == 0,
                source.data.eq(packet_id[:data_width])
            ).Elif(word_index == 1,
                source.data.eq(with_payload0)
            ).Else(
                source.data.eq(with_payload1)
            )
        ]

        # Advance on successful handshake; maintain format and counters.
        self.sync += [
            If(sent,
                If(word_index == 2,
                    word_index.eq(0),
                    packet_id.eq(packet_id + 1),
                    payload_counter.eq(payload_counter + 2)
                ).Else(
                    word_index.eq(word_index + 1)
                )
            )
        ]