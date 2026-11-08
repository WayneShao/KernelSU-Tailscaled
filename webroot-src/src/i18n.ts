export type Language = "en" | "zh-CN";

let language: Language = "en";
try {
  if (localStorage.getItem("kst-language") === "zh-CN") language = "zh-CN";
} catch {
  // Some manager WebViews disable storage; the session still supports switching.
}
document.documentElement.lang = language;

export function getLanguage(): Language { return language; }

export function setLanguage(value: Language): void {
  language = value;
  document.documentElement.lang = value;
  try { localStorage.setItem("kst-language", value); } catch { /* Session-only preference. */ }
}

export function t(english: string, chinese: string): string {
  return language === "zh-CN" ? chinese : english;
}

export function appendLanguageSelector(header: HTMLElement): void {
  const label = document.createElement("label");
  label.className = "language-selector";
  label.append(t("Language", "语言"));
  const select = document.createElement("select");
  select.dataset.language = "";
  for (const [value, text] of [["en", "English"], ["zh-CN", "简体中文"]]) {
    const option = document.createElement("option");
    option.value = value!;
    option.textContent = text!;
    select.append(option);
  }
  select.value = language;
  label.append(select);
  header.append(label);
}
