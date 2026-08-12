import i18n from "i18next";
import LanguageDetector from "i18next-browser-languagedetector";
import { initReactI18next } from "react-i18next";

import enAdmin from "./locales/en/admin.json";
import enAnomalies from "./locales/en/anomalies.json";
import enCategories from "./locales/en/categories.json";
import enChat from "./locales/en/chat.json";
import enClassification from "./locales/en/classification.json";
import enCommon from "./locales/en/common.json";
import enCostSaving from "./locales/en/costSaving.json";
import enDashboard from "./locales/en/dashboard.json";
import enDocumentView from "./locales/en/documentView.json";
import enDocuments from "./locales/en/documents.json";
import enDuplicates from "./locales/en/duplicates.json";
import enErrors from "./locales/en/errors.json";
import enLogin from "./locales/en/login.json";
import enSearch from "./locales/en/search.json";

import itAdmin from "./locales/it/admin.json";
import itAnomalies from "./locales/it/anomalies.json";
import itCategories from "./locales/it/categories.json";
import itChat from "./locales/it/chat.json";
import itClassification from "./locales/it/classification.json";
import itCommon from "./locales/it/common.json";
import itCostSaving from "./locales/it/costSaving.json";
import itDashboard from "./locales/it/dashboard.json";
import itDocumentView from "./locales/it/documentView.json";
import itDocuments from "./locales/it/documents.json";
import itDuplicates from "./locales/it/duplicates.json";
import itErrors from "./locales/it/errors.json";
import itLogin from "./locales/it/login.json";
import itSearch from "./locales/it/search.json";

export const SUPPORTED_LANGUAGES = ["en", "it"] as const;
export type SupportedLanguage = (typeof SUPPORTED_LANGUAGES)[number];

const resources = {
  en: {
    common: enCommon,
    login: enLogin,
    dashboard: enDashboard,
    documents: enDocuments,
    documentView: enDocumentView,
    categories: enCategories,
    classification: enClassification,
    search: enSearch,
    chat: enChat,
    costSaving: enCostSaving,
    anomalies: enAnomalies,
    duplicates: enDuplicates,
    admin: enAdmin,
    errors: enErrors,
  },
  it: {
    common: itCommon,
    login: itLogin,
    dashboard: itDashboard,
    documents: itDocuments,
    documentView: itDocumentView,
    categories: itCategories,
    classification: itClassification,
    search: itSearch,
    chat: itChat,
    costSaving: itCostSaving,
    anomalies: itAnomalies,
    duplicates: itDuplicates,
    admin: itAdmin,
    errors: itErrors,
  },
};

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    fallbackLng: "en",
    supportedLngs: SUPPORTED_LANGUAGES as unknown as string[],
    ns: Object.keys(resources.en),
    defaultNS: "common",
    interpolation: { escapeValue: false },
    detection: {
      order: ["localStorage", "navigator"],
      lookupLocalStorage: "language",
      caches: ["localStorage"],
    },
  });

// <html lang> is the single source of truth for the document's declared
// language - keep it in sync here instead of duplicating the assignment in
// every place the language can change (switcher, detector on first load).
document.documentElement.lang = i18n.resolvedLanguage ?? "en";
i18n.on("languageChanged", (lng) => {
  document.documentElement.lang = lng;
});

export default i18n;
