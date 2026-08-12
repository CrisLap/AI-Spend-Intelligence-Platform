// Fails if the en/ and it/ locale bundles have drifted apart - a key added
// to one language and forgotten in the other silently falls back to
// fallbackLng ("en") at runtime instead of erroring, so this has to be
// caught here instead.
import { readdirSync, readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const localesDir = path.join(__dirname, "..", "src", "i18n", "locales");

function flattenKeys(obj, prefix = "") {
  return Object.entries(obj).flatMap(([key, value]) => {
    const fullKey = prefix ? `${prefix}.${key}` : key;
    if (value !== null && typeof value === "object" && !Array.isArray(value)) {
      return flattenKeys(value, fullKey);
    }
    return [fullKey];
  });
}

const enDir = path.join(localesDir, "en");
const files = readdirSync(enDir).filter((f) => f.endsWith(".json"));

let hasDrift = false;

for (const file of files) {
  const enPath = path.join(localesDir, "en", file);
  const itPath = path.join(localesDir, "it", file);

  const enKeys = new Set(flattenKeys(JSON.parse(readFileSync(enPath, "utf-8"))));
  const itKeys = new Set(flattenKeys(JSON.parse(readFileSync(itPath, "utf-8"))));

  const missingInIt = [...enKeys].filter((k) => !itKeys.has(k));
  const missingInEn = [...itKeys].filter((k) => !enKeys.has(k));

  if (missingInIt.length || missingInEn.length) {
    hasDrift = true;
    console.error(`\nKey mismatch in ${file}:`);
    for (const k of missingInIt) console.error(`  missing in it/${file}: ${k}`);
    for (const k of missingInEn) console.error(`  missing in en/${file}: ${k}`);
  }
}

if (hasDrift) {
  console.error("\ni18n parity check failed - see mismatches above.");
  process.exit(1);
} else {
  console.log(`i18n parity check passed (${files.length} namespaces, en/it in sync).`);
}
