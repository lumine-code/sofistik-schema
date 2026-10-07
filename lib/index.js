const { getGrammarVocabulary, readMetadata } = require("./catalog");
const { SofistikSchemaProvider, SofistikReleaseSchema } = require("./provider");

let defaultProvider = null;

function provider() {
  defaultProvider ||= new SofistikSchemaProvider();
  return defaultProvider;
}

function getMetadata() {
  return readMetadata();
}

module.exports = {
  SofistikSchemaProvider,
  SofistikReleaseSchema,
  getGrammarVocabulary,
  getMetadata,
  provider,
};
