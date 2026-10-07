# sofistik-schema

Provides versioned SOFiSTiK CADINP command schemas.

> **NOTE**: This package is not an official SOFiSTiK product and is not affiliated with or endorsed by SOFiSTiK AG.

## Features

- **Versioned schemas**: preserves every CADINP command form and its ordered slots for each supported release and language.
- **Keyword indexes**: derives compact module, command, item, and enum lookups from the canonical schemas.
- **Module identities**: distinguishes source catalogue names from public executable aliases.
- **Tree-sitter vocabulary**: exposes a deterministic union and digest for parser generation.
- **Lazy API**: loads only the release and language a consumer requests.

## Installation

Install the library from an immutable Git commit:

```sh
npm install github:lumine-code/sofistik-schema#<commit-sha>
```

The package is distributed through Git pins and is not published to the npm registry.

## Usage

```js
const { SofistikSchemaProvider } = require("@lumine-code/sofistik-schema");

const data = new SofistikSchemaProvider();
const keywords = data.forRelease("2026", "en");
const aquaCommands = keywords.getModuleCommands("AQUA");
const concreteForms = keywords.getCommandSchema("AQUA", "CONC").forms;
```

`forRelease` requires an explicit supported release and returns `null` for a release or language absent from the committed data. Languages are `en` and `de`, case-insensitively; omitting the language selects English. Dataset lookup never searches installations or definitions and never substitutes a different release.

Consumers compose this library with [sofistik-context](https://github.com/lumine-code/sofistik-context) when they need file declarations and installation discovery:

```js
const { SofistikContextResolver } = require("@lumine-code/sofistik-context");
const resolver = new SofistikContextResolver({
  fallbackVersion: () => data.getAvailableVersions().at(-1),
});
const environment = resolver.resolve({
  filePath: "C:/Projects/Bridge/model.dat",
});
const context = data.forRelease(environment.version, environment.language);
```

An offline dataset fallback belongs to the consumer's policy. Native database consumers can resolve installations without loading this library. Explicitly selected unsupported releases remain exact and produce no keyword context.

## Building

The canonical schemas are committed under `schema/`. Run `npm run generate` to rebuild the compact command indexes, metadata and semantic digests.

Each schema slot retains its nativePrefix from the source catalogue before the marker is normalized into kind. An unmarked source slot has an empty string; a synthesized slot without source syntax has null. This preserves distinctions such as plain parameters versus ! identifiers and = fields without claiming that the marker alone defines a numeric type. Existing kind, units and enum metadata remain available alongside it.

Refreshing schemas from an installed SOFiSTiK release is an explicit local pipeline:

```sh
python build/0_copyerr.py --root "C:/Program Files/SOFiSTiK"
python build/1_extract.py
python build/3_merge.py
npm test
```

`SOFISTIK_ROOT` may replace `--root`. The licensed `.err` catalogues remain under ignored `build/<release>/` directories and are never committed or packed.

## Contributing

Got ideas to make this package better, found a bug, or want to help add new features? Just drop your thoughts on GitHub. Any feedback is welcome!
