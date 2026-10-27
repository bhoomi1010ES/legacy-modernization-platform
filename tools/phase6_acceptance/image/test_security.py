"""Independent assertions of the actual Phase 6 container isolation settings."""

import errno
import json
import os
from pathlib import Path
import socket

import pytest


def test_container_restrictions() -> None:
    status = dict(
        line.split(":", 1)
        for line in Path("/proc/self/status").read_text().splitlines()
        if ":" in line
    )
    interfaces = sorted(path.name for path in Path("/sys/class/net").iterdir())
    assert interfaces == ["lo"]
    assert os.getuid() == 65534 and os.getgid() == 65534
    assert int(status["CapEff"].strip(), 16) == 0
    assert status["NoNewPrivs"].strip() == "1"
    assert Path("/sys/fs/cgroup/memory.max").read_text().strip() == "268435456"
    assert Path("/sys/fs/cgroup/pids.max").read_text().strip() == "64"
    quota, period = Path("/sys/fs/cgroup/cpu.max").read_text().split()
    assert int(quota) == int(period)
    with pytest.raises(OSError) as caught:
        Path("/root-write-probe").write_text("must not be possible")
    assert caught.value.errno == errno.EROFS
    assert not Path("/app").exists()
    assert not any(
        any(
            word in key.upper()
            for word in ("PASSWORD", "SECRET", "TOKEN", "API_KEY", "DATABASE_URL")
        )
        for key in os.environ
    )
    with socket.socket() as probe:
        probe.settimeout(0.2)
        with pytest.raises(OSError):
            probe.connect(("192.0.2.1", 443))
    print(
        json.dumps(
            {
                "container_hostname": socket.gethostname(),
                "uid": os.getuid(),
                "gid": os.getgid(),
                "interfaces": interfaces,
                "capabilities": status["CapEff"].strip(),
                "no_new_privileges": status["NoNewPrivs"].strip(),
                "memory_bytes": 268435456,
                "cpu_count": 1,
                "pids_max": 64,
                "root_read_only": True,
                "credential_variables_absent": True,
            },
            sort_keys=True,
        )
    )
