# sofistik-data

Provides versioned SOFiSTiK CADINP command and schema data.

> **NOTE**: This package is not an official SOFiSTiK product and is not affiliated with or endorsed by SOFiSTiK AG.

## Features

- **Versioned schemas**: preserves every CADINP command form and its ordered slots for each supported release and language.
- **Keyword indexes**: derives compact module, command, item, and enum lookups from the canonical schemas.
- **Module identities**: distinguishes source catalogue names from public executable aliases.
- **Tree-sitter vocabulary**: exposes a deterministic union and digest for parser generation.
- **Lazy API**: loads only the release and language a consumer requests.
- **Environment resolver**: extends the lightweight sofistik-env library with exact keyword selection and an offline dataset fallback.

## Installation

Install the library from an immutable Git commit:

```sh
npm install github:lumine-code/sofistik-data#<commit-sha>
```

The package is distributed through Git pins and is not published to the npm registry.

## Usage

```js
const { SofistikDataProvider } = require("@lumine-code/sofistik-data");

const data = new SofistikDataProvider();
const keywords = data.forRelease("2026", "en");
const aquaCommands = keywords.getModuleCommands("AQUA");
const concreteForms = keywords.getCommandSchema("AQUA", "CONC").forms;
```

`forRelease` returns `null` for a release or language absent from the committed data. Omitting a release selects the newest available dataset, and omitting a language selects English.

`resolveProjectTarget({ definitionText, defaultVersion })` remains available as a pure helper for callers that deliberately select from a definition, an explicit fallback, and bundled data. It returns `{ version, source, dataSupported }`, with `source` equal to `definition`, `setting`, or `bundled`. Empty and `Auto` fallbacks are ignored; unsupported selected years remain exact. Runtime consumers use the environment resolver below to include installation discovery.

`SofistikEnvironmentResolver` extends [sofistik-env](https://github.com/lumine-code/sofistik-env) for consumers that need keyword data. Native consumers that only need installation discovery can use that small library directly. It uses an explicit caller year, `SOF_VERSION` from `sofistik.def` alongside the actual file, the newest actually installed release, then the newest bundled dataset. Its fixed installation root is `C:\Program Files\SOFiSTiK`; installation paths are `<root>/<year>/SOFiSTiK <year>`. Missing installations are reported with `installed: false`, while unsupported selected years stay exact with `dataSupported: false`. `getKeywordContext(context)` uses that exact year and returns `null` when no dataset exists.

`resolve({ filePath, directoryPath, projectPath, version, language, edition })` returns `{ version, language, edition, root, installPath, installed, dataSupported, versionSource }`. Every argument is optional. `versionSource` is `explicit`, `definition`, `installed`, or `bundled`. A supplied `filePath` always selects only `sofistik.def` in that file's directory; missing adjacent definitions never fall through to a workspace root or ancestor. Files in different directories may therefore use different releases, languages and editions. Without a file path, `directoryPath` selects an explicit directory, `projectPath` remains its compatibility fallback, and the working directory is the final default. Source files and their headers are never read for detection. Explicit `language` wins over `SOF_LANGUAGE = EN` or `DE`, then English. Explicit `edition` wins over `SOF_EDITION = professional` or `educational`, then Professional. These definition keys are integration declarations, not a claim that SOFiSTiK itself interprets them.

Definitions are read fresh on each resolution. Installed releases must contain a calculation executable or a CDB interface; an empty leftover directory is ignored. The installed-release list is cached for at most five seconds; `clearCache()` invalidates it immediately. The resolver accepts injectable filesystem functions, an installation root and clock through its constructor for testing. It neither loads a native interface nor executes a calculation.

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
