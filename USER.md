# SPP Adatbetöltő — Felhasználói dokumentáció

## Mi ez az alkalmazás?

Az **SPP Adatbetöltő** a Shopper Park Plus és Shopper Retail Park pénzügyi adatainak feldolgozó eszköze. Segítségével banki, szállítói és vevői fizetési adatok tölthetők be Excel/UMS fájlokból az SQL Server adatbázisba.

---

## Indítás

Kattints duplán a `run.bat` fájlra. Az alkalmazás teljes képernyőn nyílik meg.

> Ha hibaüzenet jelenik meg induláskor, ellenőrizd, hogy az adatbázis szerver elérhető-e a hálózaton.

---

## Navigáció

A bal oldali sötét sávon (sidebar) választhatók ki a nézetek:

| Szekció | Funkció |
|---|---|
| **Kezdőlap** | Összefoglaló — staging táblák aktuális állapota |
| **BANK → Lekérdezés** | Bank_stage tábla megtekintése, history-ba mentés, törlés |
| **BANK → Importálás** | Banki .UMS fájlok betöltése |
| **SZÁLLÍTÓ → Lekérdezés** | Szállítói staging tábla kezelése |
| **SZÁLLÍTÓ → Importálás (.XLS)** | Irems szállítói XLS export betöltése |
| **SZÁLLÍTÓ → Importálás (.XLSX)** | Irems szállítói XLSX export betöltése |
| **VEVŐ → Lekérdezés** | Vevői staging tábla kezelése |
| **VEVŐ → Importálás (.XLS)** | Irems vevői XLS export betöltése |
| **VEVŐ → Importálás (.XLSX)** | Irems vevői XLSX export betöltése |
| **BEÁLLÍTÁSOK → Bankszámlaszám** | Bankszámlaszám törzsadatok kezelése |
| **BEÁLLÍTÁSOK → Belső kód** | Bank belső kód törzsadatok kezelése |
| **BEÁLLÍTÁSOK → Partnerek** | UMS–Combosoft partner párosítás kezelése |

---

## Importálás (Bank / Szállító / Vevő)

A folyamat minden entitásnál azonos:

### 1. Fájl kiválasztása
Kattints a **„Fájlok kiválasztása"** (vagy „Fájl kiválasztása") gombra, és válaszd ki a betöltendő fájl(oka)t.

- **Bank (.UMS):** több fájl egyszerre is betölthető — az adatok összegződnek
- **Szállító/Vevő (.XLS és .XLSX):** szintén több fájl, illetve egyszerre 1 XLSX

A betöltött fájlok neve megjelenik a bal panelen. Ugyanaz a fájl kétszer nem tölthető be.

### 2. Adatok ellenőrzése
A betöltés után a jobb oldalon táblázatban látszanak az adatok. Ellenőrizd, hogy minden rendben van-e (dátumok, összegek, partnernevek).

### 3. Mentés az adatbázisba
Kattints a **„Mentés"** gombra.

- Az alkalmazás elvégzi az automatikus validációt (dátumformátum, kötelező mezők, deviza stb.)
- Ha hiba van, piros sorokban jelzi, és hibaüzenetben leírja a problémát
- Sikeres mentés után az adatok a staging táblába kerülnek, az UI visszaáll alapállapotba

### 4. Visszaállítás (opcionális)
A **„Visszaállítás"** gomb törli a betöltött adatokat az UI-ból (az adatbázist nem érinti).

---

## Lekérdezés (Bank / Szállító / Vevő)

### Adatok megtekintése
Kattints a **„Lekérdezés"** gombra — a staging tábla aktuális tartalma betöltődik a táblázatba.

### Mentés history-ba
Ha az adatok rendben vannak, kattints a **„Mentés history-ba"** gombra. A dátumválasztóban látható dátum (alapértelmezetten a mai nap) kerül be a könyvelési dátumként.

> A history-ba mentés a tárolt eljárást hívja meg, amely véglegesíti az adatokat.

### Törlés
A **„Törlés"** gomb eltávolítja a staging tábla összes sorát (megerősítés után). Ezt akkor érdemes használni, ha hibás adatok kerültek be és újra kell importálni.

---

## Beállítások

A beállítások nézetekben (Bankszámlaszám / Belső kód / Partnerek) törzsadatok kezelhetők.

### Adatok betöltése
Kattints a **„Lekérdezés"** gombra.

### Sor szerkesztése
Kattints egy sorra a táblázatban — a jobb panelen megjelennek a mező értékei, amelyek szerkeszthetővé válnak. Módosítás után kattints a **„Mentés"** gombra.

### Új sor hozzáadása
Kattints az **„Új sor"** gombra, töltsd ki a jobb panel mezőit, majd kattints a **„Mentés"** gombra.

### Sor törlése
Jelöld ki a törölni kívánt sort (vagy sorokat), majd kattints a **„Törlés (N)"** gombra. Megerősítés után a sor törlésre kerül.

### Exportálás
Az **„Exportálás"** gomb az aktuális táblatartalmat Excel fájlba menti az `exports/` mappába (időbélyeges fájlnévvel).

### UMS szinkron (csak Partnerek nézetben)
Az **„UMS szinkron"** gomb automatikusan beolvassa a banki adatokból az ismeretlen partnerneveket és hozzáadja a listához. Ezután a Combosoft partner mező kézzel tölthető ki.

A **„Hiányzó Combosoft"** gomb azokat a sorokat exportálja, ahol a Combosoft partner mező még nincs kitöltve.

---

## Tipikus munkafolyamat

```
1. Bankszámlaadatok importálása:
   BANK → Importálás → fájl kiválasztása → Mentés

2. Adatok ellenőrzése és jóváhagyása:
   BANK → Lekérdezés → Mentés history-ba

3. Szállítói/vevői adatokkal ugyanígy.

4. Ha hiba volt, a staging törölhető:
   Lekérdezés → Törlés → visszatérés az importáláshoz
```

---

## Hibaelhárítás

| Hiba | Teendő |
|---|---|
| „Adatbázis hiba" induláskor | Ellenőrizd a hálózati kapcsolatot és a VPN-t |
| „Fejléc eltérés" importálásnál | A fájl nem az elvárt formátumú; kérj új exportot |
| Piros sorok a táblázatban | Validációs hiba — az üzenet leírja a problémát |
| „Nincs adat" a lekérdezésnél | A staging tábla üres; előbb importálni kell |

---

*SPP Adatbetöltő — Belső használatra*
