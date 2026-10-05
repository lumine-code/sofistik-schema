const fs = require("fs");
const path = require("path");

const {
  buildGrammarVocabulary,
  commandSlots,
  digest,
  projectCommandSchema,
  readJson,
  repositoryRoot,
  semanticJson,
} = require("../lib/catalog");

const DATASET_PATTERN = /^sofistik\.(\d{4})\.(de|en)\.json$/;
const SLOT_KINDS = new Set([
  "keyword",
  "literal",
  "enum",
  "comment",
  "placeholder",
]);
const ENUM_VALUE_PATTERN = /^[A-Z0-9_().=*+/\->]+$/;
const NATIVE_PREFIXES = new Set(["", "'", '"', "`", "!", "=", null]);

function writeJson(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, `${JSON.stringify(value, null, 2)}\n`);
}

function discoverDatasets(root) {
  const schemaDirectory = path.join(root, "schema");
  const datasets = new Map();
  for (const filename of fs.readdirSync(schemaDirectory).sort()) {
    const match = filename.match(DATASET_PATTERN);
    if (!match) {
      if (filename !== "meta.json" && filename.startsWith("sofistik.")) {
        throw new Error(`Invalid schema dataset filename ${filename}`);
      }
      continue;
    }
    datasets.set(`${match[1]}.${match[2]}`, {
      filename,
      language: match[2],
      schema: readJson(path.join(schemaDirectory, filename)),
      version: match[1],
    });
  }
  if (datasets.size === 0) throw new Error("No SOFiSTiK schemas found");
  return datasets;
}

function validateSchema(schema, filename) {
  for (const [moduleName, commands] of Object.entries(schema)) {
    if (!/^[A-Z][A-Z0-9_]*$/.test(moduleName)) {
      throw new Error(`${filename}: invalid module ${moduleName}`);
    }
    for (const [commandName, command] of Object.entries(commands)) {
      if (
        !/^[A-Z][A-Z0-9_]*$/.test(commandName) ||
        !Array.isArray(command.forms)
      ) {
        throw new Error(
          `${filename}: invalid command ${moduleName}.${commandName}`,
        );
      }
      const fingerprints = command.forms.map(semanticJson);
      if (new Set(fingerprints).size !== fingerprints.length) {
        throw new Error(
          `${filename}: ${moduleName}.${commandName} has duplicate forms`,
        );
      }
      command.forms.forEach((form, formIndex) => {
        if (!form || typeof form !== "object" || !Array.isArray(form.slots)) {
          throw new Error(
            `${filename}: ${moduleName}.${commandName} form ${formIndex + 1} is invalid`,
          );
        }
        form.slots.forEach((slot, slotIndex) => {
          const location = `${filename}: ${moduleName}.${commandName} form ${formIndex + 1} slot ${slotIndex + 1}`;
          if (slot.position !== slotIndex + 1)
            throw new Error(`${location} has invalid position`);
          if (slot.kind === "placeholder" && slot.name !== null) {
            throw new Error(`${location} has a named placeholder`);
          }
          if (slot.kind !== "placeholder" && typeof slot.name !== "string") {
            throw new Error(`${location} has an unnamed ${slot.kind} slot`);
          }
          if (slot.name !== null && !/^[A-Z][A-Z0-9_+/-]*$/.test(slot.name)) {
            throw new Error(`${location} has invalid name`);
          }
          if (slot.name === "XXXX")
            throw new Error(`${location} exposes a placeholder as an item`);
          if (!SLOT_KINDS.has(slot.kind))
            throw new Error(`${location} has invalid kind`);
          if (
            slot.nativePrefix !== undefined &&
            !NATIVE_PREFIXES.has(slot.nativePrefix)
          )
            throw new Error(`${location} has invalid native prefix`);
          if (
            slot.dataTypeCode !== null &&
            !/^\d{4}$/.test(slot.dataTypeCode)
          ) {
            throw new Error(
              `${location} has invalid data type ${slot.dataTypeCode}`,
            );
          }
          if (!Array.isArray(slot.enumValues))
            throw new Error(`${location} has invalid enums`);
          if (
            slot.enumValues.some(
              (value) =>
                typeof value !== "string" ||
                !ENUM_VALUE_PATTERN.test(value) ||
                value !== value.toUpperCase() ||
                value === "XXXX" ||
                value === "OBS." ||
                /^\.{2,}\d*$/.test(value),
            ) ||
            JSON.stringify(slot.enumValues) !==
              JSON.stringify([...new Set(slot.enumValues)].sort())
          ) {
            throw new Error(`${location} has non-canonical enums`);
          }
          if (
            slot.enumRedirect !== null &&
            (typeof slot.enumRedirect !== "object" ||
              typeof slot.enumRedirect.command !== "string" ||
              typeof slot.enumRedirect.item !== "string" ||
              !/^[A-Z][A-Z0-9_]*$/.test(slot.enumRedirect.command) ||
              !/^[A-Z][A-Z0-9_]*$/.test(slot.enumRedirect.item))
          ) {
            throw new Error(`${location} has invalid enum redirect`);
          }

          if (slot.enumRedirect === null) return;
          const targetCommand =
            commands[slot.enumRedirect.command] ||
            schema.BASIC?.[slot.enumRedirect.command];
          const targetSlot = targetCommand
            ? commandSlots(targetCommand).find(
                (candidate) => candidate.name === slot.enumRedirect.item,
              )
            : null;
          if (!targetSlot) {
            throw new Error(
              `${location} targets missing redirect ${slot.enumRedirect.command}.${slot.enumRedirect.item}`,
            );
          }
        });
      });
    }
  }
}

function expandAllowedRedirects(entries) {
  return entries.flatMap((entry) =>
    entry.versions.map((version) => ({
      version,
      language: entry.language,
      module: entry.module,
      command: entry.command,
      form: entry.form,
      position: entry.position,
      item: entry.item,
      target: entry.target,
    })),
  );
}

function validateAliases(metadata, datasets) {
  const modules = new Set();
  for (const { schema } of datasets.values()) {
    for (const moduleName of Object.keys(schema)) modules.add(moduleName);
  }
  for (const [kind, aliases] of [
    ["Source", metadata.sourceModuleAliases],
    ["Public", metadata.publicModuleAliases],
  ]) {
    for (const [alias, target] of Object.entries(aliases)) {
      if (
        !/^[A-Z][A-Z0-9_]*$/.test(alias) ||
        !/^[A-Z][A-Z0-9_]*$/.test(target)
      ) {
        throw new Error(
          `${kind} alias ${alias} -> ${target} has invalid spelling`,
        );
      }
      if (modules.has(alias))
        throw new Error(
          `${kind} alias ${alias} conflicts with a schema module`,
        );
      if (!modules.has(target))
        throw new Error(
          `${kind} alias ${alias} targets missing module ${target}`,
        );
    }
  }
}

function unresolvedRedirectCount(schema) {
  let count = 0;
  for (const commands of Object.values(schema)) {
    for (const command of Object.values(commands)) {
      for (const slot of commandSlots(command)) {
        if (slot.enumRedirect !== null && slot.enumValues.length === 0)
          count += 1;
      }
    }
  }
  return count;
}

function findUnresolvedRedirects(dataset) {
  const result = [];
  for (const [moduleName, commands] of Object.entries(dataset.schema)) {
    for (const [commandName, command] of Object.entries(commands)) {
      for (const [formIndex, form] of command.forms.entries()) {
        for (const slot of form.slots) {
          if (slot.enumRedirect !== null && slot.enumValues.length === 0) {
            result.push({
              version: dataset.version,
              language: dataset.language,
              module: moduleName,
              command: commandName,
              form: formIndex + 1,
              position: slot.position,
              item: slot.name,
              target: slot.enumRedirect,
            });
          }
        }
      }
    }
  }
  return result;
}

function generateData(root = repositoryRoot) {
  const metadataFile = path.join(root, "schema", "meta.json");
  const existingMetadata = readJson(metadataFile);
  const datasets = discoverDatasets(root);
  for (const dataset of datasets.values())
    validateSchema(dataset.schema, dataset.filename);

  const versions = [
    ...new Set([...datasets.values()].map(({ version }) => version)),
  ].sort();
  const languages = [
    ...new Set([...datasets.values()].map(({ language }) => language)),
  ].sort();
  for (const version of versions) {
    for (const language of languages) {
      if (!datasets.has(`${version}.${language}`)) {
        throw new Error(`Missing schema for ${version}.${language}`);
      }
    }
  }

  const metadataBase = {
    formatVersion: 2,
    versions,
    languages,
    sourceModuleAliases: existingMetadata.sourceModuleAliases || {},
    publicModuleAliases: existingMetadata.publicModuleAliases || {},
    provenance: existingMetadata.provenance || {},
    allowedUnresolvedRedirects:
      existingMetadata.allowedUnresolvedRedirects || [],
  };
  validateAliases(metadataBase, datasets);

  const unresolvedRedirects = {};
  const unresolvedLocations = [];
  const semanticSchemas = {};
  for (const [key, dataset] of datasets) {
    unresolvedRedirects[key] = unresolvedRedirectCount(dataset.schema);
    unresolvedLocations.push(...findUnresolvedRedirects(dataset));
    semanticSchemas[dataset.filename] = dataset.schema;
    writeJson(
      path.join(root, "commands", dataset.filename),
      projectCommandSchema(dataset.schema),
    );
  }

  const expectedUnresolved = expandAllowedRedirects(
    metadataBase.allowedUnresolvedRedirects,
  );
  const unresolvedKeys = (locations) => locations.map(semanticJson).sort();
  if (
    JSON.stringify(unresolvedKeys(expectedUnresolved)) !==
    JSON.stringify(unresolvedKeys(unresolvedLocations))
  ) {
    throw new Error(
      "Unresolved enum redirects differ from the explicit allowlist",
    );
  }

  const vocabulary = buildGrammarVocabulary(
    metadataBase,
    (version, language) => datasets.get(`${version}.${language}`).schema,
  );
  const metadata = {
    ...metadataBase,
    unresolvedRedirects,
    schemaDigest: digest(semanticSchemas),
    grammarVocabularyDigest: vocabulary.digest,
  };
  writeJson(metadataFile, metadata);

  return { datasets: datasets.size, metadata, vocabulary };
}

if (require.main === module) {
  const result = generateData();
  process.stdout.write(
    `Generated ${result.datasets} datasets; schema ${result.metadata.schemaDigest}; vocabulary ${result.vocabulary.digest}.\n`,
  );
}

module.exports = { discoverDatasets, generateData, validateSchema, writeJson };
