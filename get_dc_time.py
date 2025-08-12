#!/usr/bin/env python3
import argparse
import platform
import re
import subprocess
from datetime import datetime, timedelta, timezone


def set_local_time(time_str: str):
    """
    time_str 格式示例：'2025-08-12 13:14:22.000000' 或 '2025-08-12 13:14:22'
    解析字符串后调用 date -s 设置时间（仅支持 Linux）
    """
    system = platform.system()
    if system != "Linux":
        print(f"Unsupported OS for set_local_time: {system}")
        return

    # 尝试解析时间字符串
    try:
        dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S.%f")
    except ValueError:
        # 如果没微秒部分，尝试无微秒格式
        try:
            dt = datetime.strptime(time_str, "%Y-%m-%d %H:%M:%S")
        except Exception as e:
            print(f"Failed to parse time string '{time_str}': {e}")
            return

    formatted_time = dt.strftime("%Y-%m-%d %H:%M:%S")

    try:
        cmd = ["sudo", "date", "-s", formatted_time]
        subprocess.check_call(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        print(f"Local time set to: {formatted_time}")
    except subprocess.CalledProcessError as e:
        print(f"Failed to set local time: {e}")
        print("Make sure to run this script with root privileges.")


def query_ldap(dc_ip):
    cmd = [
        "ldapsearch",
        "-x",
        "-H",
        f"ldap://{dc_ip}",
        "-b",
        "",
        "-s",
        "base",
        "currentTime",
    ]
    try:
        output = subprocess.check_output(cmd, text=True)
    except Exception as e:
        return False, f"LDAP query failed: {e}"

    for line in output.splitlines():
        if line.startswith("currentTime:"):
            s = line.split()[1]
            try:
                dt = datetime.strptime(s, "%Y%m%d%H%M%S.%fZ").replace(
                    tzinfo=timezone.utc
                )
                dt_local = dt.astimezone(timezone(timedelta(hours=8)))
                return True, dt_local.strftime("%Y-%m-%d %H:%M:%S.%f")
            except Exception as e:
                return False, f"Failed to parse LDAP time: {e}"
    return False, "No currentTime found in LDAP response"


def query_ntp(dc_ip):
    try:
        output = subprocess.check_output(["ntpdate", "-q", dc_ip], text=True)
        first_line = output.splitlines()[0]
        m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)", first_line)
        if m:
            return True, m.group(1)
        else:
            return False, "Cannot parse ntpdate output time"
    except Exception as e:
        return False, f"NTP query failed: {e}"


def query_http(dc_ip):
    cmd = ["htpdate", "-q", dc_ip]
    try:
        output = subprocess.check_output(cmd, text=True)
        offset = None
        for line in output.splitlines():
            if "Offset" in line:
                offset = float(line.split()[1])
                break
        if offset is None:
            return False, "Offset not found from htpdate output"
        import time

        t = int(time.time() + offset)
        dt = datetime.fromtimestamp(t)
        return True, dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        return False, f"HTTP date query failed: {e}"


def query_smb(dc_ip):
    cmd = ["net", "time", "system", "-S", dc_ip]
    try:
        output = subprocess.check_output(cmd, text=True).strip()
        m = re.match(
            r"(?P<mo>\d{2})(?P<da>\d{2})(?P<h>\d{2})(?P<mi>\d{2})(?P<yr>\d{4})\.(?P<sec>\d+)",
            output,
        )
        if not m:
            return False, f"Unexpected net time output format: {output}"
        yr = int(m.group("yr"))
        mo = int(m.group("mo"))
        da = int(m.group("da"))
        h = int(m.group("h"))
        mi = int(m.group("mi"))
        sec = int(m.group("sec"))
        dt = datetime(yr, mo, da, h, mi, sec)
        return True, dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception as e:
        return False, f"SMB time query failed: {e}"


def main():
    parser = argparse.ArgumentParser(description="Query Domain Controller Time")
    parser.add_argument(
        "-t",
        "--type",
        choices=["ldap", "ntp", "http", "smb"],
        help="Query method (optional). If not provided, try LDAP, SMB, NTP, HTTP in order",
    )
    parser.add_argument(
        "-debug",
        action="store_true",
        help="Enable debug output showing each query attempt result",
    )
    parser.add_argument(
        "-s",
        "--set-time",
        action="store_true",
        help="Set local system time to queried time (Linux only, requires root)",
    )
    parser.add_argument("dc_ip", help="Domain Controller IP or hostname")
    args = parser.parse_args()

    query_funcs = {
        "ldap": query_ldap,
        "smb": query_smb,
        "ntp": query_ntp,
        "http": query_http,
    }

    time_str = None
    if args.type:
        success, result = query_funcs[args.type](args.dc_ip)
        if success:
            time_str = result
        else:
            if args.debug:
                print(f"{args.type.upper()} query failed: {result}")
    else:
        for method in ["ldap", "smb", "ntp", "http"]:
            success, result = query_funcs[method](args.dc_ip)
            if args.debug:
                print(
                    f"Trying {method.upper()}: {'Success' if success else 'Fail'} - {result}"
                )
            if success:
                time_str = result
                break
        else:
            print("All query methods failed.")

    if time_str:
        print(time_str)
        if args.set_time:
            set_local_time(time_str)


if __name__ == "__main__":
    main()
