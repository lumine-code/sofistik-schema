const fs = require("fs");
const path = require("path");

const {
  getGrammarVocabulary,
  readMetadata,
  repositoryRoot,
} = require("./catalog");

class SofistikReleaseSchema {
  constructor(baseProvider, version, language) {
    this.base = baseProvider;
    this.version = version;
    this.language = language;
  }

  getVersion() {
    return this.version;
  }

  getLanguage() {
    return this.language;
  }

  getKeywords() {
    return this.base.loadKeywords(this.version, this.language);
  }

  getModuleKeywords(moduleName) {
    const keywords = this.getKeywords();
    return keywords[this.base.normalizeModuleName(moduleName)] || null;
  }

  getModuleNames() {
    const moduleNames = Object.keys(this.getKeywords());
    for (const [alias, target] of Object.entries(
      this.base.publicModuleAliases,
    )) {
      if (moduleNames.includes(target) && !moduleNames.includes(alias))
        moduleNames.push(alias);
    }
    return moduleNames;
  }

  getModuleCommands(moduleName) {
    const module = this.getModuleKeywords(moduleName);
    return module ? Object.keys(module) : [];
  }

  getCommandKeywords(moduleName, commandName) {
    const module = this.getModuleKeywords(moduleName);
    return module?.[String(commandName).toUpperCase()] || null;
  }

  getCommandSchema(moduleName, commandName) {
    const schemas = this.base.loadSchemas(this.version, this.language);
    const module = schemas[this.base.normalizeModuleName(moduleName)];
    return module?.[String(commandName).toUpperCase()] || null;
  }

  getCommandParams(moduleName, commandName) {
    const params = this.getCommandKeywords(moduleName, commandName);
    return params ? Object.keys(params) : [];
  }

  getParamEnums(moduleName, commandName, paramName) {
    const params = this.getCommandKeywords(moduleName, commandName);
    const normalizedParam = String(paramName).toUpperCase();
    return params && normalizedParam in params ? params[normalizedParam] : null;
  }

  searchKeyword(keyword) {
    const results = [];
    const searchTerm = String(keyword).toUpperCase();
    for (const [moduleName, module] of Object.entries(this.getKeywords())) {
      for (const [commandName, params] of Object.entries(module)) {
        if (commandName.includes(searchTerm)) {
          results.push({
            module: moduleName,
            command: commandName,
            type: "command",
          });
        }
        for (const paramName of Object.keys(params || {})) {
          if (paramName.includes(searchTerm)) {
            results.push({
              module: moduleName,
              command: commandName,
              keyword: paramName,
              type: "param",
            });
          }
        }
      }
    }
    return results;
  }

  validateKeyword(word) {
    const searchTerm = String(word).toUpperCase();
    for (const [moduleName, module] of Object.entries(this.getKeywords())) {
      if (module[searchTerm]) {
        return {
          module: moduleName,
          command: searchTerm,
          type: "command",
          params: module[searchTerm],
        };
      }
      for (const [commandName, params] of Object.entries(module)) {
        if (params && searchTerm in params) {
          return {
            module: moduleName,
            command: commandName,
            keyword: searchTerm,
            type: "param",
            enumValues: params[searchTerm],
          };
        }
      }
    }
    return null;
  }

  getStatistics() {
    const stats = {
      version: this.version,
      language: this.language,
      totalModules: 0,
      totalCommands: 0,
      totalSubKeywords: 0,
      moduleStats: {},
    };
    for (const [moduleName, module] of Object.entries(this.getKeywords())) {
      const commands = Object.keys(module).length;
      const subKeywords = Object.values(module).reduce(
        (sum, params) => sum + Object.keys(params || {}).length,
        0,
      );
      stats.totalModules += 1;
      stats.totalCommands += commands;
      stats.totalSubKeywords += subKeywords;
      stats.moduleStats[moduleName] = { commands, subKeywords };
    }
    return stats;
  }
}

class SofistikSchemaProvider {
  constructor(options = {}) {
    this.root = options.root || repositoryRoot;
    this.cache = {};
    this.schemaCache = {};
    this._metadata = null;
    this.publicModuleAliases = {};
  }

  getMetadata() {
    if (!this._metadata) {
      this._metadata = readMetadata(this.root);
      this.publicModuleAliases = this._metadata.publicModuleAliases || {};
    }
    return this._metadata;
  }

  getAvailableVersions() {
    return [...this.getMetadata().versions];
  }

  getGrammarVocabulary() {
    return getGrammarVocabulary(this.root);
  }

  forRelease(version, language = "en") {
    const metadata = this.getMetadata();
    const release = String(version ?? "").trim();
    const locale = String(language).trim().toLowerCase();
    if (
      !metadata.versions.includes(release) ||
      !metadata.languages.includes(locale)
    )
      return null;
    return new SofistikReleaseSchema(this, release, locale);
  }

  normalizeModuleName(moduleName) {
    this.getMetadata();
    const normalized = String(moduleName).trim().toUpperCase();
    return this.publicModuleAliases[normalized] || normalized;
  }

  loadKeywords(version, language) {
    const cacheKey = `${version}.${language}`;
    if (this.cache[cacheKey]) return this.cache[cacheKey];

    const file = path.join(this.root, "commands", `sofistik.${cacheKey}.json`);
    const rawData = JSON.parse(fs.readFileSync(file, "utf8"));
    const result = {};
    for (const [moduleName, moduleData] of Object.entries(rawData)) {
      result[moduleName] = {};
      for (const [commandName, paramsList] of Object.entries(moduleData)) {
        result[moduleName][commandName] = this.parseParamsList(paramsList);
      }
    }
    this.cache[cacheKey] = result;
    return result;
  }

  loadSchemas(version, language) {
    const cacheKey = `${version}.${language}`;
    if (this.schemaCache[cacheKey]) return this.schemaCache[cacheKey];
    const file = path.join(this.root, "schema", `sofistik.${cacheKey}.json`);
    this.schemaCache[cacheKey] = JSON.parse(fs.readFileSync(file, "utf8"));
    return this.schemaCache[cacheKey];
  }

  parseParamsList(paramsList) {
    const result = {};
    for (let index = 0; index < paramsList.length; index += 1) {
      const item = paramsList[index];
      if (typeof item !== "string") continue;
      if (Array.isArray(paramsList[index + 1])) {
        result[item] = paramsList[index + 1];
        index += 1;
      } else {
        result[item] = null;
      }
    }
    return result;
  }

  clearCache() {
    this.cache = {};
    this.schemaCache = {};
    this._metadata = null;
    this.publicModuleAliases = {};
  }
}

module.exports = { SofistikSchemaProvider, SofistikReleaseSchema };
