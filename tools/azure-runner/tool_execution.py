"""Route product programs to the isolated worker, never to the controller OS."""
from contextvars import ContextVar
import base64
import json
import os
from pathlib import Path
import shlex
import subprocess
from isolated_tools import IsolationError

CURRENT = ContextVar("lantern_tool_worker", default=None)
_GIT_IDENTITY = {"GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"}
_SAFE_ENV = {"GIT_NO_REPLACE_OBJECTS": "1", "GIT_TERMINAL_PROMPT": "0",
             "GIT_CONFIG_NOSYSTEM": "1", "GIT_CONFIG_GLOBAL": "/dev/null",
             "GIT_OPTIONAL_LOCKS": "0", "GIT_PAGER": "cat", "CI": "1"}
# ASCII framing prevents the worker's text decoder from corrupting Git blob
# bytes. Truncated framing fails rather than masquerading as a valid blob.
_BINARY_RUNNER = """import base64,json,os,subprocess,sys
p=json.loads(base64.b64decode(sys.argv[1]))
r=subprocess.run(p['argv'],cwd=p['cwd'],env={**os.environ,**p['env']},
 input=base64.b64decode(p['input']) if p['input'] is not None else None,
 stdin=None if p['input'] is not None else subprocess.DEVNULL,
 stdout=subprocess.PIPE,stderr=subprocess.PIPE)
print(json.dumps({'version':1,'stdout':base64.b64encode(r.stdout).decode(),
                  'stderr':base64.b64encode(r.stderr).decode()}))
sys.exit(r.returncode if r.returncode >= 0 else 128-r.returncode)
"""


def enabled():
    return os.environ.get("LANTERN_ISOLATED_TOOLS") == "1" or os.environ.get("LANTERN_EXECUTOR") == "isolated"


def worker_for(root):
    worker = CURRENT.get()
    if worker is None or root is None:
        return None
    root = Path(root).resolve()
    return worker if root == worker.product_root or worker.product_root in root.parents else None


def _translate(arg, worker):
    value = str(arg)
    path = Path(value)
    if path.is_absolute():
        path = path.resolve()
        for root, inside in ((worker.product_root, "/work/product"),
                             (worker.output_root, "/work/media")):
            if path == root or root in path.parents:
                suffix = path.relative_to(root).as_posix()
                return inside if suffix == "." else inside + "/" + suffix
    return value


def _environment(given, worker):
    # No provider, DB, Docker, loader or arbitrary Git env crosses. Fixed safe
    # values cannot be weakened by inherited controller settings.
    selected = {key: str(value) for key, value in given.items() if key in _GIT_IDENTITY}
    selected.update(_SAFE_ENV)
    if "GIT_INDEX_FILE" in given:
        value = Path(given["GIT_INDEX_FILE"])
        if not value.is_absolute():
            value = worker.product_root / value
        value = value.resolve()
        if not value.is_relative_to(worker.product_root):
            raise IsolationError("Git temporary index must remain inside the product mount")
        selected["GIT_INDEX_FILE"] = _translate(value, worker)
    return selected


def run(argv, *, cwd=None, **kwargs):
    worker = worker_for(cwd)
    if worker is None:
        if enabled() or CURRENT.get() is not None:
            raise IsolationError("isolated product execution requires its bound worker and product cwd")
        return subprocess.run(argv, cwd=cwd, **kwargs)
    if isinstance(argv, (str, bytes)) or not argv:
        raise ValueError("Isolated product commands require an argument list")
    allowed = {"env", "input", "timeout", "check", "text", "encoding", "errors",
               "universal_newlines", "capture_output", "stdin", "stdout", "stderr"}
    if set(kwargs) - allowed:
        raise ValueError("Unsupported isolated subprocess options: " + ", ".join(sorted(set(kwargs) - allowed)))
    if kwargs.get("stdin") not in (None, subprocess.DEVNULL):
        raise ValueError("Isolated stdin must use explicit input or DEVNULL")
    if kwargs.get("stdout") not in (None, subprocess.PIPE, subprocess.DEVNULL) or kwargs.get("stderr") not in (
            None, subprocess.PIPE, subprocess.DEVNULL, subprocess.STDOUT):
        raise ValueError("Isolated subprocesses cannot inherit host file descriptors")
    text_mode = bool(kwargs.get("text") or kwargs.get("encoding") or kwargs.get("universal_newlines"))
    translated = [_translate(arg, worker) for arg in argv]
    if Path(translated[0]).name == "git":
        # Docker Desktop bind mounts can report a different owner. Trust only
        # this execution's selected checkout; never use safe.directory=*.
        translated[1:1] = ["-c", "safe.directory=/work/product"]
    selected = _environment(kwargs.get("env") or {}, worker)
    data = kwargs.get("input")
    if isinstance(data, str):
        data = data.encode(kwargs.get("encoding") or "utf-8", kwargs.get("errors") or "strict")
    directory = _translate(Path(cwd).resolve(), worker)
    if text_mode:
        command = "cd " + shlex.quote(directory) + " && " + shlex.join([
            "env", *(f"{key}={value}" for key, value in selected.items()), *translated])
        if data is not None:
            command = "printf %s " + shlex.quote(base64.b64encode(data).decode()) + " | base64 -d | (" + command + ")"
    else:
        payload = {"argv": translated, "cwd": directory, "env": selected,
                   "input": base64.b64encode(data).decode() if data is not None else None}
        encoded = base64.b64encode(json.dumps(payload).encode()).decode()
        command = shlex.join(["/opt/lantern/venv/bin/python", "-I", "-c", _BINARY_RUNNER, encoded])
    observed = worker.run(command, timeout_s=kwargs.get("timeout", 300))
    if text_mode:
        stdout, stderr = observed.stdout, observed.stderr
    else:
        try:
            envelope = json.loads(observed.stdout)
            if set(envelope) != {"version", "stdout", "stderr"} or envelope["version"] != 1:
                raise ValueError("unexpected binary transport shape")
            stdout, stderr = (base64.b64decode(envelope[key], validate=True) for key in ("stdout", "stderr"))
        except (ValueError, TypeError, KeyError) as exc:
            raise IsolationError("Binary worker output is incomplete or malformed; refusing corrupted evidence") from exc
    if kwargs.get("stderr") == subprocess.STDOUT:
        stdout += stderr
        stderr = None
    result = subprocess.CompletedProcess(argv, observed.returncode, stdout, stderr)
    if kwargs.get("check") and result.returncode:
        raise subprocess.CalledProcessError(result.returncode, argv, result.stdout, result.stderr)
    return result


def shell(command, root, timeout):
    worker = worker_for(root)
    if (enabled() or CURRENT.get() is not None) and worker is None:
        raise IsolationError("isolated tool execution requires a bound worker")
    return worker.run(command, timeout_s=timeout) if worker else None


def file_route(path, *, product_root=None):
    """Select a mount lexically, before any attacker-controlled path resolution.

    A post-policy symlink swap must never redirect the controller's own file IO.
    The Linux helper below resolves components only inside the worker namespace.
    """
    path = Path(os.path.abspath(path))
    worker = CURRENT.get()
    if worker is not None:
        for root, inside in ((worker.product_root, "/work/product"),
                             (worker.output_root, "/work/media")):
            if path == root or root in path.parents:
                return inside, path.relative_to(root).parts
    if (enabled() or worker is not None) and product_root is not None:
        root = Path(os.path.abspath(product_root))
        if path == root or root in path.parents:
            raise IsolationError("Worker-owned product file access requires its bound worker")
    return None


_FILE_RUNNER = """import base64,json,os,stat,sys
p=json.loads(base64.b64decode(sys.argv[1]))
fds=[]
try:
 parts=p['parts']; op=p['operation']; limit=p['limit']
 if p['root'] not in ('/work/product','/work/media') or any(x in ('','..','.') or '/' in x for x in parts):
  raise ValueError('invalid worker file path')
 current=os.open(p['root'],os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW); fds.append(current)
 directories=parts if op=='list' else parts[:-1]
 for part in directories:
  if op in ('write','append'):
   try: os.mkdir(part,dir_fd=current)
   except FileExistsError: pass
  current=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=current); fds.append(current)
 if op=='list':
  entries=[]
  for name in os.listdir(current):
   if len(entries)>=200: raise ValueError('directory exceeds 200 entries; use scoped Git inspection')
   info=os.stat(name,dir_fd=current,follow_symlinks=False)
   entries.append({'name':name,'is_dir':stat.S_ISDIR(info.st_mode)})
  value=entries
 else:
  if not parts: raise ValueError('choose a file inside the worker mount')
  flags=os.O_NOFOLLOW|os.O_NONBLOCK
  flags|=os.O_RDONLY if op=='read' else os.O_WRONLY|os.O_CREAT
  descriptor=os.open(parts[-1],flags,0o600,dir_fd=current); fds.append(descriptor)
  info=os.fstat(descriptor)
  if not stat.S_ISREG(info.st_mode) or info.st_nlink!=1: raise PermissionError('only ordinary unlinked files are allowed')
  if op=='read':
   data=os.read(descriptor,limit+1)
   if len(data)>limit and not p.get('truncate'): raise ValueError('file exceeds bounded read; use scoped Git inspection')
   data=data[:limit]
   value=base64.b64encode(data).decode()
  elif op in ('write','append'):
   data=base64.b64decode(p['content'],validate=True)
   if op=='write': os.ftruncate(descriptor,0)
   else: os.lseek(descriptor,0,os.SEEK_END)
   remaining=memoryview(data)
   while remaining: remaining=remaining[os.write(descriptor,remaining):]
   value=len(data)
  else: raise ValueError('invalid file operation')
 message=json.dumps({'ok':True,'value':value})
 if len(message)>110000: raise ValueError('directory output exceeds bounded read')
 print(message)
except (OSError,ValueError) as error:
 print(json.dumps({'ok':False,'error':type(error).__name__,'message':str(error)[:500]}))
 sys.exit(1)
finally:
 for descriptor in reversed(fds): os.close(descriptor)
"""


def file_io(operation, path, *, content=None, max_bytes=60_000, truncate=False):
    """Perform policy-approved product/media IO inside the isolated namespace."""
    worker = CURRENT.get()
    route = file_route(path)
    if worker is None or route is None:
        raise IsolationError("Worker file IO requires a bound product or media mount")
    if operation not in {"read", "list", "write", "append"} or not 0 < max_bytes <= 60_000:
        raise ValueError("Unsupported worker file operation or read limit")
    root, parts = route
    payload = {"root": root, "parts": parts, "operation": operation, "limit": max_bytes, "truncate": bool(truncate),
               "content": base64.b64encode(content.encode("utf-8")).decode() if content is not None else None}
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    result = worker.run(shlex.join(["/opt/lantern/venv/bin/python", "-I", "-c", _FILE_RUNNER, encoded]),
                        timeout_s=30)
    try:
        response = json.loads(result.stdout)
        if not response["ok"]:
            error = {"PermissionError": PermissionError, "FileNotFoundError": FileNotFoundError,
                     "ValueError": ValueError}.get(response.get("error"), OSError)
            raise error(response.get("message", "worker file operation failed"))
        if result.returncode:
            raise IsolationError("Worker file IO returned contradictory status")
        value = response["value"]
        return base64.b64decode(value, validate=True).decode("utf-8", errors="replace" if truncate else "strict") if operation == "read" else value
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise IsolationError("Worker file output is incomplete or malformed") from exc
