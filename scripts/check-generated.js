const fs = require("fs");
const os = require("os");
const path = require("path");

const { repositoryRoot, semanticJson } = require("../lib/catalog");
const { generateData } = require("./generate-data");

function files(directory) {
  return fs
    .readdirSync(directory, { withFileTypes: true })
    .filter((entry) => entry.isFile())
    .map((entry) => entry.name)
    .sort();
}

function compareDirectory(expectedRoot, actualRoot, relativeDirectory) {
  const expectedDirectory = path.join(expectedRoot, relativeDirectory);
  const actualDirectory = path.join(actualRoot, relativeDirectory);
  const expectedFiles = files(expectedDirectory);
  const actualFiles = files(actualDirectory);
  if (JSON.stringify(expectedFiles) !== JSON.stringify(actualFiles)) {
    throw new Error(`${relativeDirectory} file list is not generated`);
  }
  for (const filename of expectedFiles) {
    const expected = JSON.parse(
      fs.readFileSync(path.join(expectedDirectory, filename), "utf8"),
    );
    const actual = JSON.parse(
      fs.readFileSync(path.join(actualDirectory, filename), "utf8"),
    );
    if (semanticJson(expected) !== semanticJson(actual)) {
      throw new Error(
        `${path.join(relativeDirectory, filename)} is not generated`,
      );
    }
  }
}

const temporaryRoot = fs.mkdtempSync(
  path.join(os.tmpdir(), "sofistik-schema-generated-"),
);
const safeRoot = path.resolve(os.tmpdir());
const resolvedTemporaryRoot = path.resolve(temporaryRoot);
if (
  path.dirname(resolvedTemporaryRoot) !== safeRoot ||
  !path.basename(resolvedTemporaryRoot).startsWith("sofistik-schema-generated-")
) {
  throw new Error(`Unexpected temporary directory ${resolvedTemporaryRoot}`);
}
try {
  fs.cpSync(
    path.join(repositoryRoot, "schema"),
    path.join(temporaryRoot, "schema"),
    {
      recursive: true,
    },
  );
  fs.mkdirSync(path.join(temporaryRoot, "commands"));
  generateData(temporaryRoot);
  compareDirectory(repositoryRoot, temporaryRoot, "commands");
  const expectedMetadata = JSON.parse(
    fs.readFileSync(path.join(repositoryRoot, "schema", "meta.json"), "utf8"),
  );
  const actualMetadata = JSON.parse(
    fs.readFileSync(path.join(temporaryRoot, "schema", "meta.json"), "utf8"),
  );
  if (semanticJson(expectedMetadata) !== semanticJson(actualMetadata))
    throw new Error("schema/meta.json is not generated");
  process.stdout.write("Generated SOFiSTiK data is current.\n");
} finally {
  fs.rmSync(resolvedTemporaryRoot, { recursive: true, force: true });
}
