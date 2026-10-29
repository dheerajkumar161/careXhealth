import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getLang, setLang, translate } from "./index";
import { LANGUAGE_NAMES, STATIC } from "./strings";

describe("i18n", () => {
  beforeEach(() => {
    localStorage.clear();
    setLang("en");
  });
  afterEach(() => vi.restoreAllMocks());

  it("returns English unchanged and never calls the server", () => {
    const f = vi.spyOn(globalThis, "fetch");
    expect(translate("Overview")).toBe("Overview");
    expect(f).not.toHaveBeenCalled();
  });

  it("uses the built-in dictionary instantly (no network)", () => {
    const f = vi.spyOn(globalThis, "fetch");
    setLang("hi");
    expect(translate("Sign out")).toBe(STATIC.hi["Sign out"]);
    expect(document.documentElement.lang).toBe("hi");
    expect(f).not.toHaveBeenCalled();
  });

  it("sets right-to-left for Arabic and Urdu and restores on English", () => {
    setLang("ar");
    expect(document.documentElement.dir).toBe("rtl");
    setLang("en");
    expect(document.documentElement.dir).toBe("ltr");
  });

  it("batches unknown strings into one /api/translate call and caches the result", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ texts: ["[gu] Take your tablet", "[gu] Drink water"], translated: true }), { status: 200 }));
    setLang("gu");
    expect(translate("Take your tablet")).toBe("Take your tablet"); // English until the server answers
    translate("Drink water");
    await vi.waitFor(() => expect(translate("Take your tablet")).toBe("[gu] Take your tablet"));
    expect(fetchMock).toHaveBeenCalledTimes(1);
    expect(JSON.parse(fetchMock.mock.calls[0][1]!.body as string)).toEqual({ texts: ["Take your tablet", "Drink water"], lang: "gu" });
    expect(JSON.parse(localStorage.getItem("cb_i18n_gu")!)["Drink water"]).toBe("[gu] Drink water");
  });

  it("falls back to English and stops asking when the server cannot translate", async () => {
    const fetchMock = vi.spyOn(globalThis, "fetch").mockResolvedValue(new Response(JSON.stringify({ texts: ["Only English"], translated: false }), { status: 200 }));
    setLang("ta");
    expect(translate("Only English")).toBe("Only English");
    await vi.waitFor(() => expect(fetchMock).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 200));
    translate("Only English");
    await new Promise((r) => setTimeout(r, 200));
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });

  it("every built-in dictionary covers the settings screen and all languages have names", () => {
    const required = ["Profile & settings", "Change password", "Language", "Save changes", "Sign out"];
    for (const [code, dict] of Object.entries(STATIC)) {
      for (const key of required) expect(dict[key], `${code}: ${key}`).toBeTruthy();
      expect(LANGUAGE_NAMES[code]).toBeTruthy();
    }
    expect(getLang()).toBe("en");
  });
});
