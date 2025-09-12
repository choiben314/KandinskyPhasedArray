# Usage:
#   sudo tcpdump -l -n -i en9 udp port 5678 and src host 192.168.1.20 -XX | awk -f udp_parse.awk

BEGIN {
  capturing = 0
  expected_payload = 0
  udp_total_len_hex = ""
  payload_hex = ""
  done_for_packet = 0
  OFS = ""
}

# lowercase a string (BSD awk has tolower()) and convert hex to byte
function hex_nibble(c,   p) {
  c = tolower(c)
  p = index("0123456789abcdef", c)
  if (p == 0) return 0
  return p - 1
}
function hex2byte(h) { return (16 * hex_nibble(substr(h,1,1)) + hex_nibble(substr(h,2,1))) }

# hex byte -> printable ASCII or '.'
function hex2ascii(h,   v) {
  v = hex2byte(h)
  if (v >= 32 && v <= 126) return sprintf("%c", v)
  return "."
}

# append 16-bit word tokens tok[i_start..n] into payload_hex as a continuous hex string
function append_tokens(i_start, n,    i) {
  for (i=i_start; i<=n; i++) payload_hex = payload_hex tok[i]
}

# when enough bytes collected, print hex and LE32; then reset
function flush_payload(   need, i, b0,b1,b2,b3,le) {
  need = expected_payload * 2
  if (length(payload_hex) < need) return

  payload_hex = substr(payload_hex, 1, need)
  print "   Payload HEX: " payload_hex

  le = ""
  for (i=1; i<=need; i+=8) {
    b0 = substr(payload_hex, i,     2)
    b1 = substr(payload_hex, i + 2, 2)
    b2 = substr(payload_hex, i + 4, 2)
    b3 = substr(payload_hex, i + 6, 2)
    le = le sprintf(" 0x%02X%02X%02X%02X",
                    hex2byte(b3),
                    hex2byte(b2),
                    hex2byte(b1),
                    hex2byte(b0))
  }
  print "   Payload LE32:" le
  print ""

  capturing = 0
  expected_payload = 0
  udp_total_len_hex = ""
  payload_hex = ""
  done_for_packet = 1
}

# ---- Summary line with src/dst/len ----
# Example: "IP 192.168.1.20.5678 > 192.168.1.1.5678: UDP, length 12"
$0 ~ / IP .* UDP, length [0-9]+/ {
  print $0

  # src is field 3, dst is field 5 (strip trailing colon)
  src_ip = $3
  dst_ip = $5
  sub(/:$/, "", dst_ip)

  # extract the length number at end of "length N"
  length_num = 0
  # scan fields to find "length" then read the next field
  for (i=1; i<=NF; i++) {
    if ($i == "length") {
      if (i+1 <= NF) length_num = $((i+1)) + 0
      break
    }
  }
  expected_payload = length_num

  print "   --- New Packet ---"
  print "   Source: " src_ip
  print "   Destination: " dst_ip
  print "   Payload length: " expected_payload " bytes"

  udp_total_len_hex = sprintf("%04x", expected_payload + 8) # UDP header is 8 bytes
  capturing = 0
  payload_hex = ""
  done_for_packet = 0

  next
}

# ---- Hex dump lines ----
# Typical: "0x0000:  00e0 4c68 00c5 ...  ASCII: ...."
# We:
#  1) print the line
#  2) take only the hex column(s) (from after colon up to the double-space before ASCII)
#  3) emit an ASCII line by converting bytes
#  4) capture payload once we've found the UDP total-length word
$0 ~ /^[[:space:]]*0x[0-9a-fA-F]+:/ {
  if (done_for_packet) next
  print $0

  line = $0
  sub(/^[[:space:]]*0x[0-9a-fA-F]+:[[:space:]]+/, "", line)

  # cut off ASCII part: find first occurrence of two+ spaces and trim there
  # (BSD awk lacks non-greedy; do a manual scan)
  cutpos = 0
  for (i=1; i<=length(line)-1; i++) {
    c1 = substr(line, i, 1)
    c2 = substr(line, i+1, 1)
    if (c1 ~ /[[:space:]]/ && c2 ~ /[[:space:]]/) { cutpos = i; break }
  }
  if (cutpos > 0) line = substr(line, 1, cutpos - 1)

  # tokenize 16-bit words (hex groups)
  n = split(line, tok, /[[:space:]]+/)

  # ASCII rendering
  ascii = "   ASCII: "
  for (i=1; i<=n; i++) {
    w = tok[i]
    if (length(w) != 4) continue
    ascii = ascii hex2ascii(substr(w,1,2)) hex2ascii(substr(w,3,2))
  }
  print ascii

  # Payload capture
  if (expected_payload > 0) {
    if (!capturing && udp_total_len_hex != "") {
      # find UDP total length word; payload starts after checksum (skip next word)
      start = -1
      for (i=1; i<=n-1; i++) {
        if (tok[i] == udp_total_len_hex) { start = i + 2; break }
      }
      if (start > 0 && start <= n) {
        capturing = 1
        append_tokens(start, n)
      }
    } else if (capturing) {
      append_tokens(1, n)
    }
    flush_payload()
  }
  next
}

# Everything else: echo through (timestamps, blank lines, etc.)
{ if (done_for_packet) next; print $0 }
