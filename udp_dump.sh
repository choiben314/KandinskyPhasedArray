#!/bin/bash

# Capture UDP packets and process them in real-time
sudo tcpdump -l -i en9 udp port 5678 and src host 192.168.1.20 -XX | while read -r line
do
    # Print the original line
    echo "$line"
    
    # Look for the BEEF/EFBE value specifically
    if [[ "$line" =~ efbe ]]; then
        echo "   DECODED: BEEF (Little-endian value detected)"
    fi
    
    # If the line contains hex data (starts with 0x)
    if [[ "$line" =~ ^0x ]]; then
        # Extract the hex data part (after the two spaces following the colon)
        hex_data=$(echo "$line" | sed -E 's/^0x[0-9a-f]+: +([0-9a-f ]+ +).*$/\1/')
        
        # Convert hex to ASCII and print readable characters
        echo -n "   ASCII: "
        for hex in $hex_data; do
            # Convert hex to decimal
            dec=$((16#$hex))
            # Print ASCII if it's a printable character (between 32 and 126), otherwise print a dot
            if [ $dec -ge 32 ] && [ $dec -le 126 ]; then
                printf "\\$(printf '%03o' $dec)"
            else
                printf "."
            fi
        done
        echo ""
        
        # Look for payload data in this line
        if [[ "$line" =~ 162e.*000c ]]; then
            # Extract the payload data after the 000c (which seems to be at the end of the header)
            payload=$(echo "$line" | grep -o '000c 0000 [0-9a-f]*' | cut -d' ' -f3-)
            if [[ ! -z "$payload" ]]; then
                echo "   Payload HEX: $payload"
                echo "   Payload decoded: $(echo $payload | sed 's/efbe/BEEF (little-endian)/')"
            fi
        fi
    fi
    
    # If the line contains a UDP packet header (IP information)
    if [[ "$line" =~ "IP ".*"UDP, length" ]]; then
        echo "   --- New Packet ---"
        # Extract relevant information if needed
        src_ip=$(echo "$line" | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}\.[a-z0-9]+' | head -1)
        dst_ip=$(echo "$line" | grep -oE '([0-9]{1,3}\.){3}[0-9]{1,3}\.[a-z0-9]+' | tail -1)
        length=$(echo "$line" | grep -oE 'length [0-9]+' | awk '{print $2}')
        echo "   Source: $src_ip"
        echo "   Destination: $dst_ip"
        echo "   Payload length: $length bytes"
    fi
done
