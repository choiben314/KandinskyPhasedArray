from litex.build.generic_platform import *
from litex.build.lattice import LatticePlatform

_io = [
    # Clk
    ("clk25", 0, Pins("P6"), IOStandard("LVCMOS33")),

    # Led
    ("user_led_n", 0, Pins("T6"), IOStandard("LVCMOS33")),

    # Button
    ("user_btn_n", 0, Pins("R7"), IOStandard("LVCMOS33")),

    # PDM Interface
    ("pdm_clk", 0, Pins("F1"), IOStandard("LVCMOS33")),
    ("pdm_data", 0, Pins("C4 D4 E4"), IOStandard("LVCMOS33")),  # Modify based on actual pinout

    # serial
    ("serial", 0,
        Subsignal("tx", Pins("T6")), # led (J19 DATA_LED-)
        Subsignal("rx", Pins("R7")), # btn (J19 KEY+)
        IOStandard("LVCMOS33")
    ),

    # SPIFlash (W25Q32JV)
    ("spiflash", 0,
        # clk
        Subsignal("cs_n", Pins("N8")),
        #Subsignal("clk",  Pins("")), driven through USRMCLK
        Subsignal("mosi", Pins("T8")),
        Subsignal("miso", Pins("T7")),
        IOStandard("LVCMOS33"),
    ),

    # RGMII Ethernet (RTL8211FD)
    ("eth_clocks", 0,
        Subsignal("tx", Pins("L1")),
        Subsignal("rx", Pins("J1")),
        IOStandard("LVCMOS33")
    ),
    ("eth", 0,
        #Subsignal("rst_n",   Pins("R6")),
        Subsignal("mdio",    Pins("T4")),
        Subsignal("mdc",     Pins("R5")),
        Subsignal("rx_ctl",  Pins("J2")),
        Subsignal("rx_data", Pins("K2 J3 K1 K3")),
        Subsignal("tx_ctl",  Pins("L2")),
        Subsignal("tx_data", Pins("M2 M1 P1 R1")),
        IOStandard("LVCMOS33")
    ),
    ("eth_clocks", 1,
        Subsignal("tx", Pins("J16")),
        Subsignal("rx", Pins("M16")),
        IOStandard("LVCMOS33")
    ),
    ("eth", 1,
        #Subsignal("rst_n",   Pins("R6")),
        Subsignal("mdio",    Pins("T4")),
        Subsignal("mdc",     Pins("R5")),
        Subsignal("rx_ctl",  Pins("P16")),
        Subsignal("rx_data", Pins("M15 R16 L15 L16")),
        Subsignal("tx_ctl",  Pins("K14")),
        Subsignal("tx_data", Pins("K16 J15 J14 K15")),
        IOStandard("LVCMOS33")
    ),
]

class Platform(LatticePlatform):
    default_clk_name = "clk25"
    default_clk_period = 1e9 / 25e6  # 25 MHz clock

    def __init__(self, **kwargs):
        LatticePlatform.__init__(self, "LFE5U-25F-6BG256C", _io, **kwargs)

    def create_programmer(self):
        return None  # Define programmer if needed