"""A stand-in for CCT-Batch.exe with the same arguments, the same CSV shape, the same console-log
side effect, and an exit code the test chooses.

CCT_STUB_PLAN names a JSON file:
    {"cameras": {"127.0.0.10": "Cam A", "127.0.0.11": "!Cam B"},
     "exit": {"127.0.2.0-127.0.2.255": 6},
     "import_exit": {"127.0.2.0-127.0.2.255": 20},
     "ignore_import": ["127.0.0.11"]}
A name starting with "!" is a camera that answers but rejects the credentials. "exit" overrides the
exit code of an export for a range, "import_exit" that of an import; otherwise 0 when a camera
logged in and 2 when none did, as CCT does.

State: the first run writes state.json beside the plan with every camera's rows. An export writes
the rows as they stand; an import replaces the rows of every camera in range that the file names,
except those in "ignore_import" - a camera that accepts the write and keeps its old value, which is
how a setting that does not take looks from outside. Each import call is recorded in imports.log.
"""
import datetime
import ipaddress
import json
import os
import sys

HEADER = ("DeviceHeader\tMacAddress\tName\tLocation\tSerialNumber\tFirmwareVersion\tModel\tManufacturer"
          "\tDHCPEnabled\tUseHttps\tPorts\tIpAddress\tSubnetMask\tDefaultGateway\tHostname"
          "\tAdminUserName\tAdminPassword",
          "AnalyticsHeader\tMacAddress\tAnalyticsEnabled")


def device_rows(n: int, ip: str, name: str) -> list[str]:
    """One camera's two rows.

    The MAC comes from the ADDRESS, never from the row's position: rows are matched by MAC, so a
    camera that is in one file and not another must not inherit its neighbour's identity. Location
    is fixed text, so renaming a camera changes exactly one column.
    """
    octets = [int(o) for o in ip.split(".")]
    mac = f"00-18-85-00-{octets[2]:02X}-{octets[3]:02X}"
    gateway = ip.rsplit(".", 1)[0] + ".1"
    return [f'Device\t{mac}\t"{name}"\t"Site"\t\'SN{n:04}\'\t"4.2.0.10"\tH4A-B\tAvigilon'
            f"\tFalse\tTrue\t80;443\t{ip}\t255.255.255.0\t{gateway}\thost{n}\t\t",
            f"Analytics\t{mac}\tTrue"]


def in_range(rng: str, ip: str) -> bool:
    lo, hi = (rng.split("-") + [rng])[:2]
    return int(ipaddress.ip_address(lo)) <= int(ipaddress.ip_address(ip)) <= int(ipaddress.ip_address(hi))


def load_state(plan: dict, state_path: str) -> dict:
    if os.path.exists(state_path):
        with open(state_path, encoding="utf-8") as handle:
            return json.load(handle)
    ordered = sorted(plan["cameras"].items(), key=lambda kv: int(ipaddress.ip_address(kv[0])))
    cameras = {}
    for n, (ip, name) in enumerate(ordered, 1):
        cameras[ip] = {"bad": name.startswith("!"), "name": name.lstrip("!"), "rows": device_rows(n, ip, name.lstrip("!"))}
    return {"cameras": cameras}


def write_console(lines: list[str]) -> None:
    log_dir = os.path.join(os.environ["LOCALAPPDATA"], "Motorola Solutions", "Camera Configuration Tool",
                           "logs", "CCT Batch")
    os.makedirs(log_dir, exist_ok=True)
    log_name = datetime.date.today().strftime("%Y-%m-%d") + "_batchconsole.log"
    with open(os.path.join(log_dir, log_name), "a", encoding="utf-8") as handle:
        handle.write("".join(line + "\n" for line in lines))


def do_export(csv: str, good: list[tuple[str, dict]], lines: list[str]) -> None:
    if not good:
        lines.append("Device not found or you use incorrect credentials")
        return
    rows = list(HEADER)
    for _, camera in good:
        rows += camera["rows"]
    with open(csv, "w", encoding="utf-16", newline="\r\n") as handle:
        handle.write("\n".join(rows) + "\n")
    lines.append(f"Number of exported devices: {len(good)}")


def rows_by_address(csv: str) -> dict[str, list[str]]:
    """The file's rows, grouped by the address in each Device row - CCT matches by MAC, and in this
    stand-in the MAC and the address agree."""
    with open(csv, encoding="utf-16") as handle:
        text = handle.read()
    grouped: dict[str, list[str]] = {}
    current = ""
    for raw in text.split("\n"):
        line = raw.rstrip("\r")
        fields = line.split("\t")
        if fields[0] == "Device":
            current = fields[11]
            grouped[current] = [line]
        elif fields[0] == "Analytics" and current:
            grouped[current].append(line)
    return grouped


def do_import(csv: str, rng: str, good: list[tuple[str, dict]], plan: dict, plan_path: str,
              lines: list[str]) -> None:
    wanted = rows_by_address(csv)
    ignore = plan.get("ignore_import", [])
    edited = 0
    for ip, camera in good:
        if ip in wanted and ip not in ignore and wanted[ip] != camera["rows"]:
            camera["rows"] = wanted[ip]
            camera["name"] = wanted[ip][0].split("\t")[2].strip('"')
            edited += 1
    lines.append(f"Number of devices in settings file: {len(wanted)}")
    lines.append(f"Number of devices available for editing: {len(good)}")
    lines.append(f"Number of edited devices: {edited}")
    if not good:
        lines.append("Device not found or you use incorrect credentials")
    with open(os.path.join(os.path.dirname(plan_path), "imports.log"), "a", encoding="utf-8") as handle:
        handle.write(f"{rng} {os.path.basename(csv)} edited={edited}\n")


def main() -> int:
    args = sys.argv[1:]
    rng = args[args.index("-a") + 1]
    plan_path = os.environ["CCT_STUB_PLAN"]
    with open(plan_path, encoding="utf-8") as handle:
        plan = json.load(handle)
    state_path = os.path.join(os.path.dirname(plan_path), "state.json")
    state = load_state(plan, state_path)
    found = {ip: camera for ip, camera in state["cameras"].items() if in_range(rng, ip)}
    ordered = sorted(found.items(), key=lambda kv: int(ipaddress.ip_address(kv[0])))

    lines = ["Start adding devices ..."]
    for ip, camera in ordered:
        status = "InvalidCredentials" if camera["bad"] else "LoggedIn"
        lines.append(f"{ip:<16}{status:<20}{camera['name']}")
    good = [(ip, camera) for ip, camera in ordered if not camera["bad"]]
    rc = 0 if good else 2

    if "-e" in args:
        do_export(args[args.index("-e") + 1], good, lines)
        rc = plan.get("exit", {}).get(rng, rc)
    elif "-i" in args:
        do_import(args[args.index("-i") + 1], rng, good, plan, plan_path, lines)
        rc = plan.get("import_exit", {}).get(rng, rc)

    for line in lines:
        print(line)
    write_console(lines)
    with open(state_path, "w", encoding="utf-8") as handle:
        json.dump(state, handle)
    return rc


if __name__ == "__main__":
    sys.exit(main())
