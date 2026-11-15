#!/usr/bin/env python3
"""Capture a QEMU screenshot through its QMP human-monitor command."""

import json
import socket
import sys
import time


def receive_message(connection: socket.socket) -> dict:
    buffer = b""
    while b"\n" not in buffer:
        chunk = connection.recv(4096)
        if not chunk:
            raise RuntimeError("QMP connection closed before a response")
        buffer += chunk
    line, _, _ = buffer.partition(b"\n")
    return json.loads(line)


def send_command(connection: socket.socket, command: dict) -> dict:
    connection.sendall(json.dumps(command).encode() + b"\r\n")
    while True:
        response = receive_message(connection)
        if "return" in response or "error" in response:
            return response


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: qmp_screendump.py QMP_SOCKET OUTPUT_PPM", file=sys.stderr)
        return 2

    socket_path, output_path = sys.argv[1:]
    deadline = time.monotonic() + 15
    while True:
        try:
            connection = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            connection.connect(socket_path)
            break
        except OSError:
            if time.monotonic() >= deadline:
                raise
            time.sleep(0.1)

    with connection:
        receive_message(connection)
        send_command(connection, {"execute": "qmp_capabilities"})
        result = send_command(
            connection,
            {
                "execute": "human-monitor-command",
                "arguments": {
                    "command-line": f"screendump {output_path}",
                },
            },
        )
    if "error" in result:
        print(json.dumps(result["error"]), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())