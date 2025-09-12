#!/usr/bin/env python3

import argparse
from typing import Any
from migen import *
from litex.gen import LiteXModule
from litex.soc.integration.soc_core import SoCMini
from litex.soc.cores.clock import ECP5PLL
from litex.soc.integration.builder import Builder
from litex.soc.interconnect import stream
from liteeth.phy.ecp5rgmii import LiteEthPHYRGMII
from liteeth.core import LiteEthUDPIPCore
from liteeth.common import convert_ip
from hw import Platform  # Your custom platform (hw.py)

# Clock and Reset Generator --------------------------------------------------------------------------------

class _CRG(LiteXModule):
    comb: Any
    specials: Any
    def __init__(self, platform, sys_clk_freq):
        self.cd_sys = ClockDomain()
        clk25 = platform.request("clk25")
        platform.add_period_constraint(clk25, 1e9 / 25e6)
        rst_n = platform.request("user_btn_n", 0)

        # PLL
        self.pll = pll = ECP5PLL()
        self.comb += pll.reset.eq(~rst_n)
        pll.register_clkin(clk25, 25e6)
        pll.create_clkout(self.cd_sys, sys_clk_freq)

# UDP Sender Module ----------------------------------------------------------------------------------------

class UDPSender(LiteXModule):
    comb: Any
    def __init__(self, ip_address, port, udp_port, data_width=32):
        # Parameters
        self.ip_address = convert_ip(ip_address)
        self.port = port
        self.data_width = data_width

        # Interfaces
        self.sink = sink = stream.Endpoint([("data", data_width)])

        # Logic to connect the sink interface to the UDP port
        self.comb += [
            udp_port.sink.valid.eq(sink.valid),
            udp_port.sink.last.eq(sink.last),
            udp_port.sink.data.eq(sink.data),
            udp_port.sink.ip_address.eq(self.ip_address),
            udp_port.sink.src_port.eq(self.port),
            udp_port.sink.dst_port.eq(self.port),
            udp_port.sink.length.eq(4),
            udp_port.sink.last_be.eq(1 << ((self.data_width // 8) - 1)),  # 0b1000 for 32-bit
            udp_port.sink.error.eq(0),
            sink.ready.eq(udp_port.sink.ready),
        ]

# Main SoC Class -------------------------------------------------------------------------------------------

class BarebonesUDP(SoCMini):
    comb: Any
    specials: Any
    submodules: Any
    platform: Any
    def __init__(self, platform, ip_address, host_ip_address, port, mac_address, sys_clk_freq=int(50e6)):
        # Clock / Reset Generator
        self.crg = _CRG(platform, sys_clk_freq)
        self.submodules.crg = self.crg  # Add to submodules

        # SoCMini Initialization
        SoCMini.__init__(self, platform, clk_freq=sys_clk_freq)

        # Ethernet PHY and UDP Core Setup
        self.ethphy = LiteEthPHYRGMII(
            clock_pads=platform.request("eth_clocks", 0),
            pads=platform.request("eth", 0),
            tx_delay=0e-9,
        )
        self.ethcore = LiteEthUDPIPCore(
            phy=self.ethphy,
            mac_address=mac_address,
            ip_address=ip_address,
            clk_freq=self.clk_freq,
            dw=32,
            with_sys_datapath=True
        )
        self.submodules += [self.ethphy, self.ethcore]

        # Timing Constraints
        eth_rx_clk = self.ethphy.crg.cd_eth_rx.clk
        eth_tx_clk = self.ethphy.crg.cd_eth_tx.clk
        self.platform.add_period_constraint(eth_rx_clk, 1e9 / self.ethphy.rx_clk_freq)
        self.platform.add_period_constraint(eth_tx_clk, 1e9 / self.ethphy.tx_clk_freq)
        self.platform.add_false_path_constraints(self.crg.cd_sys.clk, eth_rx_clk, eth_tx_clk)

        # PDM Clock (~3.125 MHz from 50 MHz sys clock)
        self.platform.add_source("cores/pdm_core.v")
        pdm_clk_sig = Signal()
        pdm_clk_pad = platform.request("pdm_clk", 0)
        self.specials += Instance("PDMCore",
            i_clk=self.crg.cd_sys.clk,
            o_pdm_clk=pdm_clk_sig
        )
        self.comb += pdm_clk_pad.eq(pdm_clk_sig)
        self.platform.add_period_constraint(pdm_clk_pad, 1e9 / (sys_clk_freq / 16))

        # UDP Port
        udp_port = self.ethcore.udp.crossbar.get_port(port, dw=32)

        # UDP Sender Module
        self.udp_sender = UDPSender(
            ip_address=host_ip_address,
            port=port,
            udp_port=udp_port,
            data_width=32,
        )
        self.submodules += self.udp_sender

        # Test Data Generator with FSM
        self.test_data_generator(sys_clk_freq)

    def test_data_generator(self, sys_clk_freq):
        # Signals
        counter = Signal(32)
        led_signal = Signal()
        send_data = Signal(32, reset=0xDEADBEEF)

        # FSM
        self.submodules.fsm = fsm = FSM(reset_state="IDLE")

        # IDLE State: Wait for counter to reach the threshold
        fsm.act("IDLE",
            NextValue(counter, counter + 1),
            If(counter >= sys_clk_freq // 1000,
                NextValue(counter, 0),
                NextState("SEND_PACKET"),
                NextValue(led_signal, ~led_signal)
            )
        )

        # SEND_PACKET State: Send the packet when ready
        fsm.act("SEND_PACKET",
            self.udp_sender.sink.valid.eq(1),
            self.udp_sender.sink.data.eq(send_data),
            self.udp_sender.sink.last.eq(1),  # Single-word packet
            If(self.udp_sender.sink.ready,
                NextState("IDLE")
            )
        )

        # LED signal
        self.comb += self.platform.request("user_led_n", 0).eq(led_signal)

# Main Function --------------------------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Kandinsky UDP Sender")
    parser.add_argument("--build", action="store_true", help="Build bitstream")
    parser.add_argument("--load", action="store_true", help="Load bitstream")
    parser.add_argument("--ip", default="192.168.1.20", help="FPGA IP address")
    parser.add_argument("--host-ip", default="192.168.1.1", help="Host IP address")
    parser.add_argument("--mac", default="0x726b895bc2e2", help="FPGA MAC address")
    parser.add_argument("--port", default=5678, type=int, help="UDP Port")

    args = parser.parse_args()

    # Instantiate platform and SoC
    platform = Platform(toolchain="trellis")
    soc = BarebonesUDP(
        platform=platform,
        ip_address=args.ip,
        host_ip_address=args.host_ip,
        port=args.port,
        mac_address=int(args.mac, 0),
    )

    # Build the design
    builder = Builder(soc, output_dir="build", csr_csv="csr.csv")
    builder.build(build_name="kandinsky", run=args.build)

    # Load the bitstream if required
    if args.load:
        prog = soc.platform.create_programmer()
        prog.load_bitstream(builder.get_bitstream_filename())

if __name__ == "__main__":
    main()