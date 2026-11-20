import i18n from "i18next";
import { initReactI18next } from "react-i18next";

const resources = {
  en: {
    translation: {
      appName: "HIMS",
      login: "Sign in",
      username: "Username",
      password: "Password",
      totp: "Authenticator code",
      logout: "Sign out",
      home: "Home",
      settings: "Facility Settings",
      users: "Users",
      roles: "Roles",
      sequences: "Number Sequences",
      audit: "Audit Logs",
      unconfirmedGst: "GSTIN is unconfirmed. A CA must verify before go-live.",
      unconfirmedTds: "TDS rate is unconfirmed. Commission math is blocked until confirmed.",
    },
  },
  hi: {
    translation: {
      appName: "HIMS",
      login: "साइन इन",
      username: "उपयोगकर्ता नाम",
      password: "पासवर्ड",
      logout: "साइन आउट",
      home: "होम",
    },
  },
  te: {
    translation: {
      appName: "HIMS",
      login: "సైన్ ఇన్",
      username: "వినియోగదారు పేరు",
      password: "పాస్‌వర్డ్",
      logout: "సైన్ అవుట్",
      home: "హోమ్",
    },
  },
};

void i18n.use(initReactI18next).init({
  resources,
  lng: "en",
  fallbackLng: "en",
  interpolation: { escapeValue: false },
});

export default i18n;
