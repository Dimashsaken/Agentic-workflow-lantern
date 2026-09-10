"""Disposable, token-free checks of existing sandbox clone/kill behavior.

This proves per-container product separation and --rm cleanup. It deliberately
does not claim that the current writable harness or credentials are contained.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import time
from uuid import uuid4


def command(*args):
    result = subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    if result.returncode:
        raise RuntimeError(result.stdout.strip())
    return result.stdout.strip()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="lantern-sandbox:agentic-infrastructure")
    parser.add_argument("--output", required=True)
    args = parser.parse_args()
    tag = uuid4().hex[:10]
    names = []
    results = {"kind": "real_container_clone_and_kill_controls", "os_containment_claim": False,
               "image_id": command("docker", "image", "inspect", args.image, "--format", "{{.Id}}")}
    with tempfile.TemporaryDirectory(prefix="lantern-isolation-") as directory:
        product = Path(directory) / "product"
        product.mkdir()
        (product / "app.txt").write_text("base\n")
        command("git", "-C", str(product), "init", "-b", "main")
        command("git", "-C", str(product), "add", ".")
        command("git", "-C", str(product), "-c", "user.name=validation", "-c",
                "user.email=validation@localhost", "-c", "commit.gpgsign=false", "commit", "-m", "base")
        original = hashlib.sha256((product / "app.txt").read_bytes()).hexdigest()
        def clone(index):
            name = f"lantern-isolation-{tag}-{index}"
            names.append(name)
            script = ("import pathlib,subprocess,time; "
                      "subprocess.run(['git','config','--global','--add','safe.directory','/product-src/.git'],check=True); "
                      "subprocess.run(['git','clone','--no-hardlinks','-q',"
                      "'/product-src','/work/product'],check=True); "
                      f"p=pathlib.Path('/work/product/app.txt'); p.write_text('{index}'); "
                      f"time.sleep(2); assert p.read_text()=='{index}'; print('isolated-{index}')")
            return command("docker", "run", "--rm", "--name", name, "--network", "none",
                           "--user", "1000:1000", "-v", f"{product}:/product-src:ro",
                           "--entrypoint", "/opt/lantern/venv/bin/python", args.image, "-c", script)
        kill_name = f"lantern-isolation-{tag}-kill"
        try:
            with ThreadPoolExecutor(max_workers=3) as pool:
                results["concurrent_clones"] = list(pool.map(clone, range(3)))
            results["source_unchanged"] = original == hashlib.sha256((product / "app.txt").read_bytes()).hexdigest()
            names.append(kill_name)
            command("docker", "run", "-d", "--rm", "--name", kill_name, "--network", "none",
                    "--user", "1000:1000", "--entrypoint", "/opt/lantern/venv/bin/python", args.image,
                    "-u", "-c", "import pathlib,time; pathlib.Path('/work/residue').write_text('test'); print('ready'); time.sleep(120)")
            for _ in range(40):
                if "ready" in command("docker", "logs", kill_name):
                    break
                time.sleep(.1)
            else:
                raise RuntimeError("kill-control never became ready")
            command("docker", "kill", kill_name)
            for _ in range(40):
                if kill_name not in command("docker", "ps", "-a", "--format", "{{.Names}}").splitlines():
                    break
                time.sleep(.1)
            results["killed_container_removed"] = kill_name not in command("docker", "ps", "-a", "--format", "{{.Names}}").splitlines()
            results["fresh_container_no_residue"] = command("docker", "run", "--rm", "--network", "none",
                "--entrypoint", "/opt/lantern/venv/bin/python", args.image, "-c",
                "from pathlib import Path; assert not Path('/work/residue').exists(); print('clean')") == "clean"
            results["passed"] = (results["concurrent_clones"] == [f"isolated-{i}" for i in range(3)] and
                results["source_unchanged"] and results["killed_container_removed"] and results["fresh_container_no_residue"])
        finally:
            # Only exact unique names created by this invocation are eligible.
            for name in names:
                subprocess.run(["docker", "rm", "-f", name], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            Path(args.output).write_text(json.dumps(results, indent=2) + "\n")
    print(json.dumps(results, indent=2))
    return results["passed"]


if __name__ == "__main__":
    raise SystemExit(0 if main() else 1)
