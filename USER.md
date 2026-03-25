# SPP Adatbetöltő — Felhasználói útmutató

Az alkalmazás banki, szállítói és vevői pénzügyi adatokat tölt be fájlokból az adatbázisba.

---

## Indítás

Kattints duplán a `run.bat` fájlra.

---

## Navigáció

A bal oldali sávon választhatók ki a funkciók:

- **Kezdőlap** — áttekintés, hány sor vár feldolgozásra
- **BANK / SZÁLLÍTÓ / VEVŐ → Importálás** — fájlok betöltése az adatbázisba
- **BANK / SZÁLLÍTÓ / VEVŐ → Lekérdezés** — betöltött adatok megtekintése, véglegesítés
- **BEÁLLÍTÁSOK** — törzsadatok karbantartása (bankszámlaszámok, belső kódok, partnerek)

---

## Adatok betöltése (Importálás)

1. Kattints a **„Fájlok kiválasztása"** gombra és válaszd ki a fájlt
2. Az adatok megjelennek a táblázatban — ellenőrizd át
3. Kattints a **„Mentés"** gombra
   - Ha valami hibás, az alkalmazás piros sorral és üzenettel jelzi
   - Sikeres mentés után az ablak visszaáll alapállapotba
4. A **„Visszaállítás"** gomb törli a táblázatot (az adatbázist nem érinti)

> Bank: több .UMS fájl egyszerre is betölthető, az adatok összeadódnak.
> Szállító/Vevő: XLS (több fájl) vagy XLSX (egyszerre 1 fájl) formátum.

---

## Adatok véglegesítése (Lekérdezés)

1. Kattints a **„Lekérdezés"** gombra — megjelennek a várakozó adatok
2. Ha minden rendben van, kattints a **„Mentés history-ba"** gombra
3. Ha hibás adatok kerültek be, a **„Törlés"** gomb üríti a táblát (majd újra importálhatsz)

---

## Beállítások

A bankszámlaszámok, belső kódok és partnerek karbantartása azonos módon működik:

- **Lekérdezés** — lista betöltése
- **Sorra kattintás** — szerkesztés a jobb panelen, majd **Mentés**
- **Új sor** — új rekord felvitele a jobb panelen, majd **Mentés**
- **Törlés (N)** — kijelölt sor(ok) törlése
- **Exportálás** — lista mentése Excel fájlba (`exports/` mappa)

**Partnerek nézetben extra funkciók:**
- **UMS szinkron** — automatikusan beolvassa a banki adatokból az ismeretlen partnerneveket
- **Hiányzó Combosoft** — exportálja azokat a sorokat, ahol a Combosoft párosítás még hiányzik

