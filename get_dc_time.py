#!/usr/bin/env python3
import argparse
import platform
import re
import subprocess
import concurrent.futures
from datetime import datetime, timedelta, timezone

# 全局超时设置：3s
QUERY_TIMEOUT = 3


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
        output = subprocess.check_output(cmd, text=True, timeout=QUERY_TIMEOUT)
    except subprocess.TimeoutExpired:
        return False, f"LDAP query timed out after {QUERY_TIMEOUT}s"
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
        output = subprocess.check_output(
            ["ntpdate", "-q", dc_ip],
            text=True,
            timeout=QUERY_TIMEOUT,
            stderr=subprocess.DEVNULL,
        )
        first_line = output.splitlines()[0]
        m = re.match(r"^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}\.\d+)", first_line)
        if m:
            return True, m.group(1)
        else:
            return False, "Cannot parse ntpdate output time"
    except subprocess.TimeoutExpired:
        return False, f"NTP query timed out after {QUERY_TIMEOUT}s"
    except Exception as e:
        return False, f"NTP query failed: {e}"


def query_http(dc_ip):
    cmd = ["htpdate", "-q", dc_ip]
    try:
        output = subprocess.check_output(cmd, text=True, timeout=QUERY_TIMEOUT)
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
    except subprocess.TimeoutExpired:
        return False, f"HTTP query timed out after {QUERY_TIMEOUT}s"
    except Exception as e:
        return False, f"HTTP date query failed: {e}"


def query_smb(dc_ip):
    cmd = ["net", "time", "system", "-S", dc_ip]
    try:
        output = subprocess.check_output(cmd, text=True, timeout=QUERY_TIMEOUT).strip()
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
    except subprocess.TimeoutExpired:
        return False, f"SMB query timed out after {QUERY_TIMEOUT}s"
    except Exception as e:
        return False, f"SMB time query failed: {e}"


def main():
    parser = argparse.ArgumentParser(description="Query Domain Controller Time")
    parser.add_argument(
        "-t",
        "--type",
        choices=["ldap", "ntp", "http", "smb"],
        help="Query method (optional). If not provided, try all methods concurrently",
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
        # 如果指定了类型，只运行单个查询
        success, result = query_funcs[args.type](args.dc_ip)
        if success:
            time_str = result
        else:
            if args.debug:
                print(f"{args.type.upper()} query failed: {result}")
    else:
        # 并发执行所有查询
        methods = ["ldap", "smb", "ntp", "http"]

        # 记录查询结果，方便在 debug 时输出
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            # 提交所有任务
            future_to_method = {
                executor.submit(query_funcs[m], args.dc_ip): m for m in methods
            }

            # as_completed 会在任意一个线程完成时 yield，谁先成功就用谁的时间
            for future in concurrent.futures.as_completed(future_to_method):
                method = future_to_method[future]
                try:
                    success, result = future.result()
                    if args.debug:
                        print(
                            f"Trying {method.upper()}: {'Success' if success else 'Fail'} - {result}"
                        )

                    # 拿到第一个成功的结果后记录下来
                    if success and not time_str:
                        time_str = result
                        # 注意：ThreadPoolExecutor 不支持直接终止正在运行的线程。
                        # 因为设置了 500ms 超时，其余线程会很快自然结束，所以直接记录结果即可。
                except Exception as e:
                    if args.debug:
                        print(f"{method.upper()} query generated an exception: {e}")

        if not time_str:
            print("All query methods failed or timed out.")

    # 最终输出并设置时间
    if time_str:
        print(time_str)
        if args.set_time:
            set_local_time(time_str)


if __name__ == "__main__":
    main()
