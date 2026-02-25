# get_dc_time

一个用于从域控制器（Domain Controller，DC）查询当前时间的 Python 脚本，支持多种查询方式，并可选在 Linux 系统上同步本地时间。

---

## 功能特点

- 支持通过 LDAP、SMB、NTP 和 HTTP 协议查询 DC 时间。
- 支持多线程并发尝试多种查询方式（LDAP、SMB、NTP、HTTP），自动采用最快返回的成功结果，且每个查询最多等待3秒（当未指定查询方式时）。
- 支持 `-s`（`--set-time`）参数，将查询到的时间同步设置到本地 Linux 系统时间。
- 支持 `-debug` 参数，开启调试模式，打印详细的命令执行和解析日志，方便排查问题。
- 主要面向 Linux 系统环境。

---

## 环境要求

- Python 3
- Linux 系统（仅支持 Linux 系统的本地时间设置功能）
- 依赖外部工具，需根据不同查询方式安装：
  - `ldapsearch` （用于 LDAP 查询）
  - `ntpdate` / `ntpdig` （用于 NTP 查询）
  - `htpdate` （用于 HTTP 查询）
  - `net`（系统自带，用于 SMB 查询）
- 设置时间时需要 root 权限或使用 `sudo`。

---

## 使用说明

```bash
python3 get_dc_time.py [选项] <dc_ip>
```

### 参数

- `<dc_ip>`
  域控制器的 IP 地址或主机名。

### 选项

- `-t, --type`
  指定查询方式，可选：`ldap`、`smb`、`ntp`、`http`。
  不指定时，默认开启4线程并发尝试 LDAP、SMB、NTP、HTTP。

- `-s, --set-time`
  将查询到的时间设置为本地系统时间（仅支持 Linux，需 root 权限）。

- `-debug`
  开启调试模式，输出详细的执行和解析信息，方便排查问题。

---

## 示例

- 默认方式查询时间（并发尝试 LDAP、SMB、NTP、HTTP，取最快响应结果）：

  ```bash
  python3 get_dc_time.py 10.10.10.5
  ```

- 指定使用 NTP 查询并同步本地时间（需 root 权限）：

  ```bash
  sudo python3 get_dc_time.py -t ntp -s 10.10.10.5
  ```

- 使用 SMB 查询并开启调试模式：

  ```bash
  python3 get_dc_time.py -t smb -debug 10.10.10.5
  ```

---

## 注意事项

- 设置系统时间需要管理员权限，请确保以 root 用户或使用 `sudo` 运行脚本。
- 脚本内部通过 `date -s` 命令设置时间，仅支持 Linux 系统。
- 请确保所需外部工具安装并在系统 PATH 中可用。
- 如果查询失败，建议启用调试模式查看具体执行细节及超时情况。
