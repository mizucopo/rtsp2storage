#!/usr/bin/env python3
"""Compare identical recording entrypoints against one isolated RTSP source."""

import argparse
from collections import Counter
from datetime import datetime
import json
import math
from pathlib import Path
import re
import subprocess
import time
import uuid


# These rates belong to the generated fixtures, not arbitrary camera streams.
FIXTURE_RATES = {"video": 25, "audio": 48000 / 1024}
START_STOP_ALLOWANCE = {"video": 3, "audio": 1}  # GOP wait (video) + pipeline drain
MAX_PACKET_GAP = {"video": 0.08, "audio": 0.05}
VARIANT_ALLOWANCE = {"video": 2.5, "audio": 1}


def docker(*args, check=True, timeout=None):
    return subprocess.run(
        ["docker", *map(str, args)], text=True, capture_output=True, check=check,
        timeout=timeout,
    )


def inspect(name):
    return json.loads(docker("inspect", name).stdout)[0]


def image_metadata(args):
    docker("pull", args.server_image)
    images = {}
    for label, image in {"baseline": args.baseline, "alpine": args.candidate,
                         "server": args.server_image}.items():
        info = inspect(image)
        images[label] = {"reference": image, "id": info["Id"],
                         "architecture": info["Architecture"]}
        if label != "server":
            run = ["run", "--rm", "--network", "none", "--platform", "linux/amd64", "--entrypoint"]
            version = docker(*run, "ffmpeg", image, "-version")
            package = docker(*run, "apk", image, "list", "--installed", "ffmpeg")
            images[label]["ffmpeg_version"] = (version.stdout + version.stderr).strip()
            images[label]["ffmpeg_package"] = package.stdout.strip() or None
    return images


def wait_for(name, marker, seconds=50):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        result = docker("logs", name)
        logs = result.stdout + result.stderr
        if marker in logs:
            return
        if not inspect(name)["State"]["Running"]:
            raise RuntimeError(f"{name} exited before {marker}: {logs}")
        time.sleep(0.5)
    raise RuntimeError(f"{name}: timed out waiting for {marker}")


def wait_for_publisher(name, url, seconds=50):
    deadline = time.monotonic() + seconds

    def require_running():
        if not inspect(name)["State"]["Running"]:
            logs = docker("logs", name)
            raise RuntimeError(f"{name} exited before RTSP readiness: {logs.stdout}{logs.stderr}")

    while (remaining := deadline - time.monotonic()) > 0:
        require_running()
        # Probe the actual path from the publisher's network. Bound both ffprobe
        # and its Docker client; exec avoids leaving an extra probe container.
        limit = min(5, remaining)
        result = docker(
            "exec", name, "timeout", "-s", "KILL", str(limit), "ffprobe",
            "-v", "error", "-rtsp_transport", "tcp", "-timeout", "1000000",
            "-analyzeduration", "1000000", "-read_intervals", "%+0.1",
            "-show_entries", "packet=stream_index", "-of", "json", url,
            check=False, timeout=limit + 1,
        )
        require_running()
        if result.returncode == 0 and json.loads(result.stdout).get("packets"):
            return
        time.sleep(min(0.5, max(0, deadline - time.monotonic())))
    raise RuntimeError(f"{name}: timed out waiting for RTSP packets at {url}")


def wait_for_recorders(names, seconds=50):
    deadline = time.monotonic() + seconds
    starts = {}
    while time.monotonic() < deadline:
        # Timestamped markers include recording before the first poll, even if
        # a Docker launch or the other recorder's preparation was slow.
        for variant, name in names.items():
            if variant in starts:
                continue
            result = docker("logs", "--timestamps", name)
            logs = result.stdout + result.stderr
            if not inspect(name)["State"]["Running"]:
                raise RuntimeError(f"{name} exited before recording readiness: {logs}")
            for line in logs.splitlines():
                if "Starting FFmpeg recording..." in line:
                    starts[variant] = docker_timestamp(line.split()[0])
                    break
        if len(starts) == len(names):
            return starts
        time.sleep(0.5)
    pending = [name for variant, name in names.items() if variant not in starts]
    raise RuntimeError(f"timed out waiting for recording start: {pending}")


def docker_timestamp(value):
    # Docker emits RFC3339Nano; Python 3.9 accepts only 3/6 fractional digits.
    normalized = re.sub(r"\.(\d+)", lambda m: "." + m[1][:6].ljust(6, "0"), value.strip())
    timestamp = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    if timestamp.tzinfo is None:
        raise ValueError("Docker timestamp must include a timezone")
    return timestamp.timestamp()


def media(args, output, program, *command):
    return docker(
        "run", "--rm", "--network", "none", "--platform", "linux/amd64",
        "-v", f"{output}:/data", "--entrypoint", program, args.candidate,
        *command, check=False,
    )


def numeric_timestamps(packets, key):
    values = []
    for packet in packets:
        try:
            value = float(packet[key])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value):
            values.append(value)
    return values


def duplicate_output_paths(logs):
    paths = Counter()
    previous_path = None
    for line in logs.splitlines():
        opening = re.search(r"Opening '(/videos/[^'\n]+\.mp4)' for writing", line)
        repeated = re.fullmatch(r"\s*Last message repeated (\d+) times?", line)
        if opening:
            previous_path = opening.group(1)
            paths[previous_path] += 1
        elif previous_path and repeated:
            paths[previous_path] += int(repeated.group(1))
        else:
            previous_path = None
    return sorted(path for path, count in paths.items() if count > 1)


def probe_outputs(args, directory, codec):
    files = []
    for path in sorted(directory.rglob("*.mp4")):
        relative = path.relative_to(directory).as_posix()
        result = media(
            args, directory, "ffprobe", "-v", "error", "-show_streams",
            "-show_format", "-show_packets", "-of", "json", f"/data/{relative}",
        )
        item = {"path": relative, "bytes": path.stat().st_size,
                "probe_exit": result.returncode, "errors": result.stderr}
        if result.returncode == 0:
            data = json.loads(result.stdout)
            item["duration"] = float(data["format"]["duration"])
            item["streams"] = []
            for stream in data["streams"]:
                packets = [p for p in data["packets"]
                           if p["stream_index"] == stream["index"]]
                dts = numeric_timestamps(packets, "dts_time")
                pts = numeric_timestamps(packets, "pts_time")
                dts_complete = bool(packets) and len(dts) == len(packets)
                pts_complete = bool(packets) and len(pts) == len(packets)
                item["streams"].append({
                    "type": stream["codec_type"], "codec": stream["codec_name"],
                    "packets": len(packets), "first_dts": dts[0] if dts else None,
                    "last_dts": dts[-1] if dts else None,
                    "min_pts": min(pts) if pts else None,
                    "dts_complete": dts_complete, "pts_complete": pts_complete,
                    "monotonic_dts": dts_complete and all(a <= b for a, b in zip(dts, dts[1:])),
                    "max_dts_gap": max((b - a for a, b in zip(dts, dts[1:])), default=0)
                    if dts_complete else None,
                    "first_keyframe": bool(packets and "K" in packets[0]["flags"]),
                })
            decode = media(
                args, directory, "ffmpeg", "-v", "error", "-xerror", "-i",
                f"/data/{relative}", "-map", "0", "-f", "null", "-",
            )
            item["decode_exit"] = decode.returncode
            item["errors"] += decode.stderr
            expected = {"h264" if codec == "h264" else "hevc", "aac"}
            item["valid"] = (
                decode.returncode == 0 and not item["errors"]
                and {s["codec"] for s in item["streams"]} == expected
                and all(s["packets"] > 0 and s["monotonic_dts"] and s["pts_complete"]
                        for s in item["streams"])
                and all(s["first_keyframe"] for s in item["streams"]
                        if s["type"] == "video")
            )
        else:
            item["valid"] = False
        files.append(item)
    return files


def recording_coverage(files, observation_seconds):
    if not math.isfinite(observation_seconds) or observation_seconds <= 0:
        raise ValueError("observation_seconds must be finite and positive")
    coverage = {"observation_seconds": observation_seconds, "streams": {}}
    for kind, rate in FIXTURE_RATES.items():
        streams = [s for f in files for s in f.get("streams", []) if s["type"] == kind]
        packets = sum(s["packets"] for s in streams)
        gaps = [s.get("max_dts_gap") for s in streams]
        complete = bool(streams) and all(
            gap is not None and math.isfinite(gap) for gap in gaps
        )
        max_gap = max(gaps) if complete else None
        packet_seconds = packets / rate
        required_seconds = max(0, observation_seconds - START_STOP_ALLOWANCE[kind])
        coverage["streams"][kind] = {
            "packets": packets, "packet_seconds": packet_seconds,
            "required_seconds": required_seconds, "max_dts_gap": max_gap,
            "allowed_dts_gap": MAX_PACKET_GAP[kind],
            "valid": complete and packet_seconds >= required_seconds
            and max_gap <= MAX_PACKET_GAP[kind] + 1e-9,
        }
    coverage["valid"] = all(s["valid"] for s in coverage["streams"].values())
    return coverage


def validate_case_coverage(case, observation_seconds):
    for name, variant in case["variants"].items():
        variant["coverage"] = recording_coverage(variant["files"], observation_seconds[name])
        variant["valid"] = variant["valid"] and variant["coverage"]["valid"]
    streams = {}
    for kind in FIXTURE_RATES:
        baseline = case["variants"]["baseline"]["coverage"]["streams"][kind]
        alpine = case["variants"]["alpine"]["coverage"]["streams"][kind]
        raw_difference = baseline["packet_seconds"] - alpine["packet_seconds"]
        observation_difference = observation_seconds["baseline"] - observation_seconds["alpine"]
        difference = abs(raw_difference - observation_difference)
        allowance = VARIANT_ALLOWANCE[kind]
        streams[kind] = {"difference_seconds": difference,
                         "raw_difference_seconds": raw_difference,
                         "observation_difference_seconds": observation_difference,
                         "allowed_seconds": allowance,
                         "valid": difference <= allowance}
    comparison = {"streams": streams,
                  "valid": all(s["valid"] for s in streams.values())}
    case["coverage_comparison"] = comparison
    for variant in case["variants"].values():
        variant["valid"] = variant["valid"] and comparison["valid"]


def run_case(args, root, network, server, codec, termination, containers):
    label = f"{codec}-{termination}"
    fixture = f"{codec}.mp4"
    publisher = f"{network}-{label}-publisher"
    containers.append(publisher)
    docker(
        "run", "-d", "--name", publisher, "--network", network,
        "--platform", "linux/amd64", "-v", f"{root}:/data:ro",
        "--entrypoint", "ffmpeg", args.candidate, "-v", "warning", "-re",
        "-stream_loop", "-1", "-i", f"/data/{fixture}", "-c", "copy",
        "-f", "rtsp", "-rtsp_transport", "tcp", f"rtsp://{server}:8554/live",
    )
    wait_for_publisher(publisher, f"rtsp://{server}:8554/live")
    names = {}
    for variant, image in (("baseline", args.baseline), ("alpine", args.candidate)):
        directory = root / label / variant
        directory.mkdir(parents=True)
        name = f"{network}-{label}-{variant}"
        names[variant] = name
        containers.append(name)
        docker(
            "run", "-d", "--name", name, "--network", network,
            "--platform", "linux/amd64", "-v", f"{directory}:/videos",
            "-e", f"RTSP_URL=rtsp://{server}:8554/live", "-e", "SEGMENT_TIME=4",
            image,
        )
    recording_starts = wait_for_recorders(names)
    observation_start = time.monotonic()
    time.sleep(13)
    running_before_stop = {variant: inspect(name)["State"]["Running"]
                           for variant, name in names.items()}
    publisher_running = inspect(publisher)["State"]["Running"]
    monotonic_observation = time.monotonic() - observation_start
    # Docker's clock matches its log timestamps; host/VM clock offsets must not
    # shorten a recorder's measured interval and hide missing packets.
    stop_requested = docker_timestamp(docker("info", "--format", "{{.SystemTime}}").stdout)
    observation_seconds = {variant: stop_requested - start
                           for variant, start in recording_starts.items()}
    if min(observation_seconds.values()) < monotonic_observation - 0.5:
        raise RuntimeError("Docker timestamps do not cover the monotonic observation window")
    if termination == "input-ended":
        docker("stop", "--time", "10", publisher)
        for name in names.values():
            deadline = time.monotonic() + 15
            while inspect(name)["State"]["Running"] and time.monotonic() < deadline:
                time.sleep(0.5)
            if inspect(name)["State"]["Running"]:
                raise RuntimeError(f"{name} did not exit after RTSP input ended")
    else:
        # This is the documented operator action, including its default grace period.
        docker("stop", "--time", "10", *names.values())
        docker("stop", "--time", "10", publisher)
    case = {"codec": codec, "termination": termination,
            "publisher_running_before_stop": publisher_running, "variants": {}}
    for variant, name in names.items():
        logs = docker("logs", name)
        log_text = logs.stdout + logs.stderr
        (root / label / f"{variant}.log").write_text(log_text)
        duplicates = duplicate_output_paths(log_text)
        files = probe_outputs(args, root / label / variant, codec)
        exit_code = inspect(name)["State"]["ExitCode"]
        case["variants"][variant] = {
            "exit_code": exit_code, "files": files,
            "running_before_stop": running_before_stop[variant],
            "duplicate_output_paths": duplicates,
            "valid": publisher_running and running_before_stop[variant]
            and exit_code == 0 and not duplicates
            and len(files) >= 3 and all(f["valid"] for f in files),
        }
    validate_case_coverage(case, observation_seconds)
    print(json.dumps({"case": label, "valid": {
        k: v["valid"] for k, v in case["variants"].items()}}), flush=True)
    return case


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", required=True)
    parser.add_argument("--candidate", required=True)
    parser.add_argument("--server-image", required=True,
                        help="MediaMTX image pinned by digest")
    parser.add_argument("--output", required=True, type=Path,
                        help="New artifact directory outside the build context")
    args = parser.parse_args()
    root = args.output.resolve()
    if root.exists():
        parser.error("--output must name a new directory")
    images = image_metadata(args)
    root.mkdir(parents=True, exist_ok=False)
    network = "rtsp2storage-compare-" + uuid.uuid4().hex[:10]
    server = network + "-server"
    containers = [server]
    report = {"segment_time": 4, "platform": "linux/amd64", "cases": [],
              "images": images}
    try:
        for codec in ("h264", "hevc"):
            encoder = "libx264" if codec == "h264" else "libx265"
            extra = ["-x265-params", "pools=2:frame-threads=2:log-level=error"] \
                if codec == "hevc" else ["-bf", "2"]
            result = media(
                args, root, "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                "testsrc2=size=320x180:rate=25", "-f", "lavfi", "-i",
                "sine=frequency=440:sample_rate=48000", "-t", "12", "-c:v",
                encoder, "-preset", "ultrafast", "-g", "50", *extra,
                "-c:a", "aac", "-ac", "2", f"/data/{codec}.mp4",
            )
            if result.returncode:
                raise RuntimeError(result.stderr)
        docker("network", "create", "--internal", network)
        docker("run", "-d", "--name", server, "--network", network, args.server_image)
        wait_for(server, "[RTSP] started with listeners", seconds=10)
        for codec in ("h264", "hevc"):
            for termination in ("input-ended", "docker-stop"):
                report["cases"].append(run_case(
                    args, root, network, server, codec, termination, containers
                ))
    finally:
        for name in containers:
            logs = docker("logs", name, check=False)
            (root / f"{name}.log").write_text(logs.stdout + logs.stderr)
            docker("rm", "-f", name, check=False)
        docker("network", "rm", network, check=False)
        (root / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    valid = all(v["valid"] for c in report["cases"] for v in c["variants"].values())
    raise SystemExit(0 if valid else 1)


if __name__ == "__main__":
    main()
