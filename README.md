## Kandinsky Acoustic Phased Array

### Install LiteX environment

```bash
wget https://raw.githubusercontent.com/enjoy-digital/litex/master/litex_setup.py
chmod +x litex_setup.py
sudo ./litex_setup.py init install
```

### Activate LiteX environment

```bash
source ~/Tools/litex/venv/bin/activate
```

### Build bitstreams

```bash
./main.py --build // builds as kandinsky
./test_udp.py --build // builds as barebones_udp
```

### Check and flash with ecpdap

```bash
ecpdap probes
ecpdap flash scan
ecpdap flash write build/gateware/{kandinsky.bit, barebones_udp.bit}
```

### Monitor Ethernet messages

```bash
./udp_monitor.sh
```
