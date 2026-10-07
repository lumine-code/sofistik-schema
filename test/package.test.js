const assert = require("node:assert/strict");
const childProcess = require("node:child_process");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");

const { repositoryRoot } = require("../lib/catalog");

function npm(arguments_, options = {}) {
  if (process.env.npm_execpath) {
    return childProcess.execFileSync(
      process.execPath,
      [process.env.npm_execpath, ...arguments_],
      {
        ...options,
        encoding: "utf8",
      },
    );
  }
  const executable = process.platform === "win32" ? "npm.cmd" : "npm";
  return childProcess.execFileSync(executable, arguments_, {
    ...options,
    encoding: "utf8",
  });
}

test("packs and installs only the supported public library", () => {
  const temporaryRoot = fs.mkdtempSync(
    path.join(os.tmpdir(), "sofistik-data-package-"),
  );
  const resolvedTemporaryRoot = path.resolve(temporaryRoot);
  assert.equal(path.dirname(resolvedTemporaryRoot), path.resolve(os.tmpdir()));
  assert.ok(
    path.basename(resolvedTemporaryRoot).startsWith("sofistik-data-package-"),
  );

  try {
    const pack = JSON.parse(
      npm(
        [
          "pack",
          "--json",
          "--ignore-scripts",
          "--pack-destination",
          temporaryRoot,
        ],
        {
          cwd: repositoryRoot,
        },
      ),
    )[0];
    const packedPaths = pack.files.map((file) => file.path);
    assert.ok(packedPaths.includes("lib/index.js"));
    assert.ok(packedPaths.includes("schema/meta.json"));
    assert.ok(packedPaths.includes("commands/sofistik.2026.en.json"));
    assert.equal(
      packedPaths.some((file) => file.toLowerCase().endsWith(".err")),
      false,
    );
    assert.equal(
      packedPaths.some((file) => file.startsWith("build/")),
      false,
    );
    assert.ok(pack.unpackedSize < 50_000_000);

    const consumer = path.join(temporaryRoot, "consumer");
    fs.mkdirSync(consumer);
    fs.writeFileSync(path.join(consumer, "package.json"), '{"private":true}\n');
    npm(
      [
        "install",
        "--ignore-scripts",
        "--no-audit",
        "--no-fund",
        path.join(temporaryRoot, pack.filename),
      ],
      { cwd: consumer },
    );

    const installed = require(
      path.join(consumer, "node_modules", "@lumine-code", "sofistik-data"),
    );
    assert.equal(installed.getMetadata().formatVersion, 2);
    assert.deepEqual(
      require(
        path.join(
          consumer,
          "node_modules",
          "@lumine-code",
          "sofistik-data",
          "package.json",
        ),
      ).dependencies || {},
      {},
    );
    const corpus = require(
      path.join(
        consumer,
        "node_modules",
        "@lumine-code",
        "sofistik-data",
        "fixtures",
        "cadinp-structure.json",
      ),
    );
    assert.ok(corpus.cases.length > 0);
    assert.ok(
      installed
        .provider()
        .forRelease("2026", "en")
        .getModuleNames()
        .includes("DBMERG"),
    );
  } finally {
    fs.rmSync(resolvedTemporaryRoot, { recursive: true, force: true });
  }
});
