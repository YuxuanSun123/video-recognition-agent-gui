import { copyFileSync, existsSync, mkdirSync, rmSync } from "node:fs";
import path from "node:path";
import process from "node:process";
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(scriptDir, "..");
const isWindows = process.platform === "win32";
const sidecarName = "backend-sidecar";

function run(command, args, options = {}) {
  console.log(`> ${command} ${args.join(" ")}`);
  const result = spawnSync(command, args, {
    cwd: root,
    stdio: "inherit",
    ...options,
  });

  if (result.error) {
    throw result.error;
  }

  if (result.status !== 0) {
    throw new Error(`${command} exited with code ${result.status}`);
  }
}

function probe(command, args) {
  const result = spawnSync(command, args, {
    cwd: root,
    encoding: "utf8",
    stdio: ["ignore", "pipe", "pipe"],
  });

  return result.status === 0 ? result.stdout.trim() : "";
}

function resolvePython() {
  const candidates = process.env.PYTHON
    ? [[process.env.PYTHON, []]]
    : isWindows
      ? [
          ["py", ["-3"]],
          ["python", []],
          ["python3", []],
        ]
      : [
          ["python3", []],
          ["python", []],
        ];

  for (const [command, baseArgs] of candidates) {
    const version = probe(command, [...baseArgs, "--version"]);
    if (version) {
      return { command, baseArgs };
    }
  }

  throw new Error("Python 3 was not found. Set PYTHON or install Python 3.10+.");
}

function runPython(python, args) {
  run(python.command, [...python.baseArgs, ...args]);
}

function getTargetTriple() {
  if (process.env.TAURI_TARGET_TRIPLE) {
    return process.env.TAURI_TARGET_TRIPLE;
  }

  const hostTuple = probe("rustc", ["--print", "host-tuple"]);
  if (hostTuple) {
    return hostTuple;
  }

  const rustcVerbose = probe("rustc", ["-Vv"]);
  const hostLine = rustcVerbose
    .split(/\r?\n/)
    .find((line) => line.trim().startsWith("host:"));

  if (hostLine) {
    return hostLine.split("host:")[1].trim();
  }

  throw new Error("Could not determine Rust target triple.");
}

function copyWithRetry(source, destination) {
  for (let attempt = 1; attempt <= 10; attempt += 1) {
    try {
      copyFileSync(source, destination);
      return;
    } catch (error) {
      if (attempt === 10) {
        throw error;
      }
      Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 700);
    }
  }
}

const python = resolvePython();
const venvDir = path.join(root, ".venv");
const venvPython = isWindows
  ? path.join(venvDir, "Scripts", "python.exe")
  : path.join(venvDir, "bin", "python");

if (!existsSync(venvPython)) {
  runPython(python, ["-m", "venv", venvDir]);
}

const targetTriple = getTargetTriple();
const targetExtension = targetTriple.includes("windows") ? ".exe" : "";
const binariesDir = path.join(root, "src-tauri", "binaries");
const destination = path.join(
  binariesDir,
  `${sidecarName}-${targetTriple}${targetExtension}`,
);

mkdirSync(binariesDir, { recursive: true });

run(venvPython, ["-m", "pip", "install", "--upgrade", "pip"]);
run(venvPython, [
  "-m",
  "pip",
  "install",
  "-r",
  path.join(root, "requirements.txt"),
  "pyinstaller",
]);

const pyinstallerArgs = [
  "-m",
  "PyInstaller",
  "--noconfirm",
  "--clean",
  "--onefile",
  "--name",
  sidecarName,
  "--collect-all",
  "dashscope",
  "--collect-all",
  "fastapi",
  "--collect-all",
  "starlette",
  "--collect-all",
  "uvicorn",
  "--hidden-import",
  "multipart",
];

if (isWindows) {
  pyinstallerArgs.push("--noconsole");
}

pyinstallerArgs.push("backend_api.py");

rmSync(path.join(root, "dist", `${sidecarName}${targetExtension}`), {
  force: true,
});

run(venvPython, pyinstallerArgs);

const builtBinary = path.join(root, "dist", `${sidecarName}${targetExtension}`);
copyWithRetry(builtBinary, destination);

console.log(`Sidecar built: ${destination}`);
