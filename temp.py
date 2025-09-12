#!/usr/bin/env python3

from migen import *
from litex.gen import *
from litex.soc.integration.soc_core import *
from litex.soc.cores.clock import *
from litex.soc.integration.builder import *
from liteeth.phy.ecp5rgmii import LiteEthPHYRGMII
from liteeth.core import LiteEthUDPIPCore
from liteeth.common import *
from hw import Platform  # Your custom platform (hw.py)

class _CRG(LiteXModule):
    def __init__(self, platform, sys_clk_freq):
        self.cd_sys = ClockDomain()
        # # #

        # Clk / Rst.
        clk25 = platform.request("clk25")
        # rst_n = platform.request("user_btn_n", 0)

        # PLL.
        self.pll = pll = ECP5PLL()
        # self.comb += pll.reset.eq(~rst_n)
        pll.register_clkin(clk25, 25e6)
        pll.create_clkout(self.cd_sys, sys_clk_freq)

class LiteEthPacketStream2UDPTX(Module):
    def __init__(self, ip_address, udp_port, data_width=32, fifo_depth=8192):
        self.sink   = sink   = stream.Endpoint(eth_tty_tx_description(data_width))
        self.source = source = stream.Endpoint(eth_udp_user_description(data_width))

        ip_address = convert_ip(ip_address)

        max_packet = 48
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
            source.length.eq(7 * 4 * max_packet),
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

class MicHub(SoCMini):
    def __init__(self, ip_address, host_ip_address, port, mac_address, sys_clk_freq=int(50e6)):
        platform = Platform(toolchain='trellis')

        # Clock / Reset Generator
        self.submodules.crg = _CRG(platform, sys_clk_freq)

        # SoC Init
        SoCMini.__init__(self, platform, clk_freq=sys_clk_freq)

        # Ethernet PHY & Core (example for networking)
        self.submodules.ethphy = LiteEthPHYRGMII(
            clock_pads=platform.request("eth_clocks", 0),
            pads=platform.request("eth", 0)
        )

        self.submodules.ethcore = LiteEthUDPIPCore(
            phy=self.ethphy,
            mac_address=mac_address,
            ip_address=ip_address,
            clk_freq=self.clk_freq,
            dw=32
        )

        # Dummy Data Generation
        dummy_data = Signal(32, reset=0x12345678)  # Example dummy data
        counter = Signal(32)  # Timer counter to generate a 1-second delay

        # 1-second timer at 50 MHz (assuming sys_clk_freq is 50 MHz)
        self.sync += [
            If(counter == sys_clk_freq - 1,  # 50,000,000 for 1 second
                counter.eq(0),
                dummy_data.eq(dummy_data + 1)  # Increment dummy data every second
            ).Else(
                counter.eq(counter + 1)
            )
        ]

        # UDP Port for sending dummy data
        udp_port = self.ethcore.udp.crossbar.get_port(port, dw=32)

        # Example UDP streamer to send the dummy data via Ethernet
        pdm_streamer = LiteEthPacketStream2UDPTX(
            ip_address=convert_ip(host_ip_address),
            udp_port=port
        )
        self.submodules += pdm_streamer

        # Combine dummy output with UDP transmission
        self.comb += [
            pdm_streamer.sink.data.eq(dummy_data),      # Send the dummy data
            pdm_streamer.sink.valid.eq(1),              # Always valid
            pdm_streamer.sink.first.eq(1),              # Mark the start of the packet
            pdm_streamer.sink.last.eq(1),               # Mark the end of the packet
            pdm_streamer.source.connect(udp_port.sink)  # Connect to UDP port
        ]

        # # Add Verilog PDM core (pdm_core.v should be in cores directory)
        platform.add_source("./cores/pdm_core.v")  # Add the Verilog source file

        # # PDM Verilog Core Instantiation
        pdm_clk = platform.request("pdm_clk")
        pdm_data = platform.request("pdm_data")  # 96-bit PDM data input

        pdm_out = Signal(32)
        pdm_valid = Signal()
        pdm_first = Signal()
        pdm_last = Signal()

        # # Instantiate the PDM core
        self.specials += Instance("PDMCore",
            i_clk=ClockSignal(),
            o_pdm_clk=pdm_clk
        )

        # Add logic to handle pdm_data, pdm_out, pdm_valid, pdm_first, and pdm_last
        # This part depends on how you want to process the PDM data
        # For example:
        # self.sync += [
        #     If(pdm_clk,
        #         pdm_out.eq(pdm_data[:32]),  # Take first 32 bits of pdm_data
        #         pdm_valid.eq(1),
        #         pdm_first.eq(1),
        #         pdm_last.eq(1)
        #     ).Else(
        #         pdm_valid.eq(0),
        #         pdm_first.eq(0),
        #         pdm_last.eq(0)
        #     )
        # ]

        # # UDP Port for sending PDM data
        # udp_port = self.ethcore.udp.crossbar.get_port(port, dw=32)

        # # Example UDP streamer to send the PDM data via Ethernet
        # pdm_streamer = LiteEthPacketStream2UDPTX(
        #     ip_address=convert_ip(host_ip_address),
        #     udp_port=port
        # )
        # self.submodules += pdm_streamer

        # # Combine PDM output with UDP transmission
        # # Connect PDM data to the UDP packet streamer's input
        # self.comb += [
        #     pdm_streamer.sink.data.eq(pdm_out),       # Connect the 32-bit PDM data to UDP input
        #     pdm_streamer.sink.valid.eq(pdm_valid),    # Only send data when valid is high
        #     pdm_streamer.sink.first.eq(pdm_first),    # Mark the start of the packet
        #     pdm_streamer.sink.last.eq(pdm_last),      # Mark the end of the packet
        #     pdm_streamer.source.connect(udp_port.sink)  # Connect the UDP streamer's output to the Ethernet port
        # ]

# Main program that builds the SoC
def main():
    parser = argparse.ArgumentParser(description="Microphone Hub")
    parser.add_argument("--build", action="store_true", help="Build bitstream")
    parser.add_argument("--load", action="store_true", help="Load bitstream")
    parser.add_argument("--ip", default="192.168.1.20", help="FPGA IP address")
    parser.add_argument("--host-ip", default="192.168.1.1", help="Host IP address")
    parser.add_argument("--mac", default="0x726b895bc2e2", help="FPGA MAC address")
    parser.add_argument("--port", default=5678, help="UDP Port")

    args = parser.parse_args()

    # Instantiate the SoC with arguments
    soc = MicHub(
        ip_address=args.ip,
        host_ip_address=args.host_ip,
        port=int(args.port),
        mac_address=int(args.mac, 0)
    )

    # Build the SoC
    builder = Builder(soc, output_dir="build", csr_csv="csr.csv")
    builder.build(build_name="michub", run=args.build)

    if args.load:
        prog = soc.platform.create_programmer()
        prog.load_bitstream(builder.get_bitstream_filename())

if __name__ == "__main__":
    main()