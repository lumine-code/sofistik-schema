const assert = require("node:assert/strict");
const childProcess = require("node:child_process");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const {
  SofistikSchemaProvider,
  getGrammarVocabulary,
  getMetadata,
} = require("../lib");
const {
  commandSlots,
  digest,
  projectCommandSchema,
  readSchema,
  repositoryRoot,
} = require("../lib/catalog");

test("publishes one complete release and language matrix", () => {
  const metadata = getMetadata();
  assert.equal(metadata.formatVersion, 2);
  assert.deepEqual(metadata.versions, [
    "2018",
    "2020",
    "2022",
    "2023",
    "2024",
    "2025",
    "2026",
  ]);
  assert.deepEqual(metadata.languages, ["de", "en"]);
  assert.match(metadata.schemaDigest, /^[a-f0-9]{64}$/);
  assert.match(metadata.grammarVocabularyDigest, /^[a-f0-9]{64}$/);
  assert.deepEqual(metadata.allowedUnresolvedRedirects, []);
  assert.ok(
    Object.values(metadata.unresolvedRedirects).every((count) => count === 0),
  );

  for (const version of metadata.versions) {
    for (const language of metadata.languages) {
      assert.ok(
        fs.existsSync(
          path.join(
            repositoryRoot,
            "schema",
            `sofistik.${version}.${language}.json`,
          ),
        ),
      );
      assert.ok(
        fs.existsSync(
          path.join(
            repositoryRoot,
            "commands",
            `sofistik.${version}.${language}.json`,
          ),
        ),
      );
    }
  }
});

test("keeps source identities separate from public executable aliases", () => {
  const metadata = getMetadata();
  assert.deepEqual(metadata.sourceModuleAliases, {
    DBIN: "DBINFO",
    MAXI: "MAXIMA",
    TEMP: "TEMPLATE",
  });
  assert.deepEqual(metadata.publicModuleAliases, {
    DBMERG: "DBME",
    STAR2: "STAR",
    TUNARS: "TUNA",
  });
});

test("derives every compact command index from its canonical schema", () => {
  const metadata = getMetadata();
  for (const version of metadata.versions) {
    for (const language of metadata.languages) {
      const projected = projectCommandSchema(readSchema(version, language));
      const committed = JSON.parse(
        fs.readFileSync(
          path.join(
            repositoryRoot,
            "commands",
            `sofistik.${version}.${language}.json`,
          ),
          "utf8",
        ),
      );
      assert.deepEqual(committed, projected, `${version}.${language}`);
    }
  }
});

test("binds contexts only to data that actually exists", () => {
  const data = new SofistikSchemaProvider();
  assert.equal(data.forRelease("2099", "en"), null);
  assert.equal(data.forRelease("2026", "pl"), null);

  const defaultContext = data.forRelease("2026");
  assert.equal(defaultContext.getVersion(), "2026");
  assert.equal(defaultContext.getLanguage(), "en");
  assert.equal(data.forRelease(), null);
  assert.equal(data.forRelease("Auto", "Auto"), null);
  assert.equal(data.forRelease("2026", "English"), null);

  const german = data.forRelease("2024", "DE");
  assert.equal(german.getVersion(), "2024");
  assert.equal(german.getLanguage(), "de");
});

test("resolves public executable module aliases", () => {
  const keywords = new SofistikSchemaProvider().forRelease("2026", "en");
  for (const [publicName, sourceName, command] of [
    ["DBMERG", "DBME", "CDB"],
    ["STAR2", "STAR", "DESI"],
    ["TUNARS", "TUNA", "GEO"],
  ]) {
    assert.ok(keywords.getModuleNames().includes(publicName));
    assert.deepEqual(
      keywords.getModuleCommands(publicName),
      keywords.getModuleCommands(sourceName),
    );
    assert.ok(
      keywords.getModuleCommands(publicName.toLowerCase()).includes(command),
    );
    assert.deepEqual(
      keywords.getCommandSchema(publicName, command),
      keywords.getCommandSchema(sourceName, command),
    );
  }
});

test("exposes ordered slots and compact enum lookups", () => {
  const keywords = new SofistikSchemaProvider().forRelease("2026", "en");
  const schema = keywords.getCommandSchema("AQUA", "CONC");
  assert.ok(schema.forms[0].slots.length > 3);
  for (const form of schema.forms) {
    assert.deepEqual(
      form.slots.map((slot) => slot.position),
      form.slots.map((_, index) => index + 1),
    );
  }
  assert.ok(keywords.getCommandParams("AQUA", "CONC").includes("TYPE"));
  assert.ok(keywords.getParamEnums("AQUA", "CONC", "type").includes("C"));
});

test("preserves distinct command forms and removes exact duplicates", () => {
  const data = new SofistikSchemaProvider();
  const current = data.forRelease("2026", "en");
  const previous = data.forRelease("2025", "en");
  assert.deepEqual(
    current
      .getCommandSchema("BDK", "EIGE")
      .forms.map((form) => form.slots.map((slot) => slot.name)),
    [
      ["TYPE", "NEIG", "LCB"],
      ["BEAM", "LC", "TYPE", "HORD", "DNO", "ENO"],
    ],
  );
  assert.equal(previous.getCommandSchema("BDK", "EIGE").forms.length, 1);

  const cuts = data
    .forRelease("2022", "en")
    .getCommandSchema("TEXTILE", "CUTS");
  assert.equal(cuts.forms.length, 1);
  assert.equal(cuts.forms[0].slots.length, 9);
});

test("preserves the positional POIN contract in every release and language", () => {
  const data = new SofistikSchemaProvider();
  const expectedNames = {
    de: [
      "REF",
      "NR",
      null,
      null,
      "BEZ",
      null,
      null,
      "PROJ",
      "WIDE",
      "NREF",
      "TYP",
      "P",
      "X",
      "Y",
      "Z",
    ],
    en: [
      "REF",
      "NO",
      null,
      null,
      "TITL",
      null,
      null,
      "PROJ",
      "WIDE",
      "NREF",
      "TYPE",
      "P",
      "X",
      "Y",
      "Z",
    ],
  };
  const expectedKinds = [
    "enum",
    "literal",
    "placeholder",
    "placeholder",
    "enum",
    "placeholder",
    "placeholder",
    "enum",
    "keyword",
    "keyword",
    "enum",
    "keyword",
    "literal",
    "keyword",
    "keyword",
  ];

  for (const version of data.getAvailableVersions()) {
    for (const language of ["de", "en"]) {
      const command = data
        .forRelease(version, language)
        .getCommandSchema("SOFILOAD", "POIN");
      assert.equal(command.forms.length, 1, `${version}.${language}`);
      const slots = command.forms[0].slots;
      assert.deepEqual(
        slots.map((slot) => slot.name),
        expectedNames[language],
        `${version}.${language}`,
      );
      assert.deepEqual(
        slots.map((slot) => slot.kind),
        expectedKinds,
        `${version}.${language}`,
      );
      assert.deepEqual(
        slots.map((slot) => slot.dataTypeCode),
        [
          null,
          null,
          null,
          null,
          null,
          null,
          null,
          null,
          "1001",
          null,
          null,
          "9999",
          "1001",
          "1001",
          "1001",
        ],
        `${version}.${language}`,
      );
    }
  }
});

test("extracts numeric, punctuated and NONE enum values without catalogue annotations", () => {
  const data = new SofistikSchemaProvider();
  const keywords = data.forRelease("2026", "en");
  const enums = (moduleName, commandName, itemName) =>
    keywords.getParamEnums(moduleName, commandName, itemName);

  assert.ok(enums("AQUA", "CTRL", "LAY").includes("0"));
  assert.ok(enums("AQUA", "CTRL", "LAY").includes("9"));
  assert.ok(enums("AQUA", "CTRL", "DIST").includes("NONE"));
  assert.ok(enums("SOFIMSHC", "GAXP", "IDS").includes("+"));
  assert.ok(enums("SOFIMSHC", "GAXP", "IDS").includes("*"));
  assert.ok(enums("SOFIMSHC", "GAXV", "TYPE").includes("D-"));
  assert.ok(enums("SOFIMSHC", "GAXV", "TYPE").includes("D+"));
  assert.ok(enums("SOFIMSHC", "GAXV", "TYPE").includes("D*"));
  assert.ok(enums("SOFIMSHC", "SLNS", "REFT").includes(">FIX"));
  assert.ok(enums("SOFIMSHC", "SLNS", "REFT").includes("+SAR"));
  assert.ok(enums("SOFIMSHC", "SLNS", "REFT").includes("*SAR"));
  assert.ok(enums("FOOTING", "TAB", "NO").includes("A6.1"));
  assert.ok(enums("DYNA", "HIST", "TYPE").includes("U-X"));
  assert.ok(enums("DYNA", "HIST", "TYPE").includes("PT/P"));
  assert.ok(enums("AQB", "CAPA", "STAT").includes("(D)"));
  assert.ok(enums("ELLA", "CALC", "PHI").includes("F18"));
  assert.ok(enums("ELLA", "CALC", "PHI").includes("F19C"));
  assert.equal(enums("DYNA", "HIST", "TYPE").includes("OBS"), false);
  assert.deepEqual(enums("TEMPLATE", "TEST", "OPT1"), [
    "=OPT1",
    "FULL",
    "NO",
    "OBS",
    "YES",
  ]);

  const legacyLink = data
    .forRelease("2018", "en")
    .getCommandSchema("HYDRA", "LINK");
  assert.deepEqual(
    legacyLink.forms[0].slots.map((slot) => slot.dataTypeCode),
    [null, "9999", "9999", "9999", null],
  );
});

test("maps letter selectors to high positional slots", () => {
  const keywords = new SofistikSchemaProvider().forRelease("2026", "en");
  const train = keywords.getCommandSchema("SOFILOAD", "TRAI").forms[0].slots;
  assert.deepEqual(
    train.slice(19, 21).map((slot) => ({
      name: slot.name,
      position: slot.position,
      values: slot.enumValues,
    })),
    [
      { name: "DIR", position: 20, values: ["B", "L", "N", "R"] },
      { name: "DIRT", position: 21, values: ["B", "L", "N", "R"] },
    ],
  );

  const group = keywords.getCommandSchema("ASE", "GRP").forms[0].slots;
  assert.deepEqual(group[20].enumValues, ["HORI", "HORX", "HORY", "VERT"]);
  assert.deepEqual(group[27].enumValues, ["ACTI", "FIX"]);

  const quad = keywords.getCommandSchema("SOFIMSHA", "QUAD");
  const redirected = commandSlots(quad).find((slot) => slot.name === "KR");
  assert.deepEqual(redirected.enumRedirect, { command: "BEAM", item: "KR" });
  assert.ok(redirected.enumValues.includes("RADI"));
});

test("preserves punctuation in directional and ratio item names", () => {
  const keywords = new SofistikSchemaProvider().forRelease("2026", "en");
  const names = (moduleName, commandName) =>
    keywords
      .getCommandSchema(moduleName, commandName)
      .forms.flatMap((form) => form.slots.map((slot) => slot.name));

  assert.ok(names("AQUA", "SMAT").includes("P+"));
  assert.ok(names("AQUA", "SMAT").includes("MY-"));
  assert.ok(names("AQUA", "SHRW").includes("SZ+"));
  assert.ok(names("SOFILOAD", "VOLU").includes("A/U"));
  assert.ok(names("TENDON", "SYSP").includes("MUE-"));
});

test("exports a deterministic grammar vocabulary digest", () => {
  const metadata = getMetadata();
  const vocabulary = getGrammarVocabulary();
  assert.equal(vocabulary.digest, metadata.grammarVocabularyDigest);
  assert.equal(vocabulary.publicModuleAliases.DBMERG, "DBME");
  assert.ok(vocabulary.modules.AQUA.CONC.includes("TYPE"));
  const semanticVocabulary = { ...vocabulary };
  delete semanticVocabulary.digest;
  assert.equal(digest(semanticVocabulary), vocabulary.digest);
});

test("projects every command form into the compact keyword union", () => {
  const schema = readSchema("2026", "en");
  const projected = projectCommandSchema(schema);
  const command = schema.BDK.EIGE;
  assert.equal(command.forms.length, 2);
  assert.ok(commandSlots(command).some((slot) => slot.name === "BEAM"));
  assert.ok(projected.BDK.EIGE.includes("BEAM"));
  assert.ok(projected.BDK.EIGE.includes("NEIG"));
});

test("semantic digests do not depend on JSON line endings or key order", () => {
  const lf = JSON.parse('{\n  "b": 2,\n  "a": 1\n}');
  const crlf = JSON.parse('{\r\n  "a": 1,\r\n  "b": 2\r\n}');
  assert.equal(digest(lf), digest(crlf));
});

test("does not track source error catalogues", () => {
  const tracked = childProcess.execFileSync("git", ["ls-files", "*.err"], {
    cwd: repositoryRoot,
    encoding: "utf8",
  });
  assert.equal(tracked.trim(), "");
});
