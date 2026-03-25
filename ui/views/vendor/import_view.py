# ui/views/vendor/import_view.py
#
# VendorImportView — Szállítói .XLS fájlok importálása.
#
# Az importált fájlok valójában HTML-alapú XLS fájlok (Irems/SAP rendszerből exportálva).
# A fájl belseje HTML táblázatot tartalmaz, amelyet pd.read_html() olvas be.
#
# Folyamat:
#   1. Fájlok kiválasztása (.xls) → HTML tartalom beolvasása pd.read_html()-lel
#   2. Fejléc ellenőrzés: az első 2 oszlop eldobása, a maradék fejléce az
#      expected_columns listával kell egyezzen
#   3. NaN sorok szűrése (Payment Amounts alapján)
#   4. Kiegészítő oszlopok kiszámítása regex segédfüggvényekkel:
#      - IBAN kinyerése az Information mezőből → formázott bankszámlaszám
#      - Fizetési dátum és ID kinyerése a Status mezőből
#      - Összeg és deviza kinyerése (Összeg/Deviza/Számlaszám triplet)
#      - Partner neve a Beneficiary mező alapján
#   5. expand_amount_paid(): egy sorból több sor (ha több összeg/deviza/számla van)
#   6. Mentés az IremsSzallito_stage táblába (bulk insert)
#
# A BaseImportView kezeli az UI logika nagy részét (fájllista, gombok, progress).

import os
import re                         # reguláris kifejezések (IBAN, dátum, ID kinyeréséhez)
import pandas as pd               # táblázatos adatkezelés
from io import StringIO           # HTML tartalom memóriából olvasásához
from itertools import zip_longest # két lista párhuzamos iterálása (különböző hossz esetén is)
from PySide6.QtWidgets import QFileDialog, QMessageBox, QApplication
from PySide6.QtCore import Qt
from models.pandas_model import PandasModel                # DataFrame → QTableView modell
from ui.dialogs.file_import_progress import ProgressDialog # fájlbeolvasási progress dialógus
from ui.views.base_import_view import BaseImportView       # közös import nézet logika


class VendorImportView(BaseImportView):
    """Szállítói .XLS fájlok importálási nézete.

    Több fájl egyszerre betölthető (akkumuláló mód). A nyers XLS fájlok
    HTML táblázatot tartalmaznak — pd.read_html() olvassa be őket.
    """

    def __init__(self):
        super().__init__()  # BaseImportView inicializálása
        self.setup_ui("Szállító adatok importálása")  # UI felépítése (BaseImportView)

        self.df_all = pd.DataFrame()  # összes betöltött fájl összesített adatai
        self.loaded_files = set()     # már betöltött fájlok abszolút útvonalai (duplikáció szűrés)

        # Az elvárt fejlécoszlopok — az első 2 oszlopot eldobjuk, ezek a maradékot
        # Ha a fájl fejléce nem egyezik ezzel, figyelmeztetés jelenik meg és a fájl kihagyásra kerül
        self.expected_columns = [
            "Information",
            "Status, Payment Date, ID",
            "Payment Amounts",
            "Payment Lines",
            "in Invoice Currency",
            "%",
            "Amount Paid",
            "Unpaid (in Inv. Crcy)",
        ]

    # -------------------------------------------------------------------------
    # BaseImportView kötelező implementációk
    # -------------------------------------------------------------------------

    def load_files(self):
        """Fájlválasztó dialógus, XLS fájlok beolvasása HTML-ként.

        A .xls fájlok valójában HTML dokumentumok (Excel .xls exportból).
        pd.read_html() megkeresi az első HTML <table> elemet és beolvassa DataFrame-be.
        Az első 2 oszlop rendszerint üres/meta adat — .iloc[:, 2:] eldobja őket.
        """
        files, _ = QFileDialog.getOpenFileNames(
            self, "Válassz .XLS fájlokat", "", "XLS fájlok (*.xls)"
        )

        if not files:
            return  # felhasználó visszalépett

        # Duplikáció szűrés: szétválasztjuk a már betöltött és az új fájlokat
        duplicates = [f for f in files if f in self.loaded_files]
        new_files = [f for f in files if f not in self.loaded_files]

        if not new_files:
            if duplicates:
                QMessageBox.warning(
                    self,
                    "Ismétlődő fájlok",
                    f"A következő fájl(ok) már be lettek olvasva:\n"
                    + "\n".join(os.path.basename(f) for f in duplicates),
                )
            return

        all_new_data = []  # új fájlok DataFrame-jei kerülnek ide
        self.loaded_files.update(new_files)  # azonnal hozzáadjuk a halmazhoz

        # Progress dialógus megjelenítése beolvasás közben
        self.progress_dialog = ProgressDialog()
        self.progress_dialog.show()
        QApplication.processEvents()  # UI frissítés kényszerítése (dialógus megjelenítéséhez)

        for file in new_files:
            filename = os.path.basename(file)

            try:
                # A .xls fájl HTML tartalomként kerül beolvasásra
                # windows-1252 kódolás: latin-1 kompatibilis (Irems exportban jellemző)
                # errors="replace": ismeretlen karakterek lecserélése, nem dob hibát
                with open(file, "r", encoding="windows-1252", errors="replace") as f:
                    html = f.read()

                # pd.read_html(): az összes HTML táblázatot listában adja vissza
                df_list = pd.read_html(StringIO(html), header=0)

                if not df_list:
                    raise ValueError("Nem találtunk HTML táblázatot.")

                # Az első táblázat, az első 2 oszlop eldobva (.iloc[:, 2:])
                # A rendszer általában sorszám és csoportosító oszlopokat tesz az elejére
                df = df_list[0].iloc[:, 2:]

                # Fejléc egyezés ellenőrzése
                if df.columns.tolist() != self.expected_columns:
                    if self.progress_dialog:
                        self.progress_dialog.accept()
                        self.progress_dialog = None
                    QMessageBox.warning(
                        self,
                        "Fejléc eltérés",
                        f"A(z) '{filename}' fájl fejlécszerkezete eltér az elvárttól, ezért kihagytuk.",
                    )
                    continue  # következő fájl

                self.loaded_files.add(file)
                self.file_list_widget.addItem(filename)  # bal panel fájllistájához hozzáadás
                all_new_data.append(df)

            except Exception as e:
                if self.progress_dialog:
                    self.progress_dialog.accept()
                    self.progress_dialog = None
                QMessageBox.warning(
                    self, "Hiba", f"{filename} beolvasása sikertelen:\n{str(e)}"
                )

        if not all_new_data:
            QMessageBox.information(
                self, "Nincs adat", "Nem található beolvasható .XLS fájl."
            )
            return

        # Az összes új fájl DataFrame-jét összefűzzük
        new_df = pd.concat(all_new_data, ignore_index=True)

        # NaN szűrés: azokat a sorokat tartjuk, ahol van Payment Amounts érték
        # (fejléc-ismétlő és üres sorok kiesnek)
        new_df = new_df.dropna(subset=["Payment Amounts"])

        # Kiegészítő oszlopok kiszámítása regex segédfüggvényekkel
        # Az Information mező formátuma: "... HUxx ... Beneficiary: Név Beneficiary Bank Acct: ..."
        new_df["Számlaszám (HU)"] = new_df["Information"].apply(self.extract_iban)
        new_df["Számlaszám (formázott)"] = new_df["Számlaszám (HU)"].apply(
            self.format_hungarian_account_number
        )
        # A Status, Payment Date, ID mező formátuma: "Executed/Submitted YYYY.MM.DD ID: 123456"
        new_df["Fizetési dátum"] = new_df["Status, Payment Date, ID"].apply(
            self.extract_payment_date
        )
        new_df["fájl"] = ""  # fájlazonosító mező (szállítóknál üres)
        new_df["Fizetési ID"] = new_df["Status, Payment Date, ID"].apply(
            self.extract_payment_id
        )
        new_df["típus"] = "Szállító"

        # expand_amount_paid(): egy sorból több sor keletkezik, ha több összeg/deviza/számla van
        # pl. "1000 HUF, 500 EUR" → 2 sor (egyenkénti összeg + deviza + számlaszám)
        new_df = self.expand_amount_paid(new_df)

        # Partner neve kinyerése
        new_df["Partner neve"] = new_df["Information"].apply(self.extract_partner_name)

        # Oszlopsorrend módosítása: Számlaszám és Partner neve pozíció csere
        cols = new_df.columns.tolist()
        idx_szamlaszam = cols.index("Számlaszám")
        idx_partner = cols.index("Partner neve")
        cols[idx_szamlaszam], cols[idx_partner] = cols[idx_partner], cols[idx_szamlaszam]
        new_df = new_df[cols]

        # Hozzáfűzzük a meglévő adatokhoz (akkumuláló mód)
        self.df_all = pd.concat([self.df_all, new_df], ignore_index=True)

        # Gombállapotok frissítése (BaseImportView)
        self._on_file_loaded()

        # Magyar számformátum: "1234.56" → "1 234,56"
        def format_thousands(val):
            try:
                number = float(str(val).replace(",", "."))
                return f"{number:,.2f}".replace(",", " ").replace(".", ",")
            except ValueError:
                return val

        self.update_table_view(
            self.df_all,
            formatters={"Összeg": format_thousands},
            alignments={"Összeg": Qt.AlignRight | Qt.AlignVCenter},  # összeg jobbra igazítva
        )

        if self.progress_dialog:
            self.progress_dialog.accept()
            self.progress_dialog = None

        if duplicates:
            QMessageBox.warning(
                self,
                "Ismétlődő fájlok",
                f"A következő fájl(ok) már be lettek olvasva:\n"
                + "\n".join(os.path.basename(f) for f in duplicates),
            )

    def get_data_for_save(self) -> pd.DataFrame:
        """Az utolsó 9 oszlopot adja vissza — ezek kerülnek az IremsSzallito_stage-be.

        A teljes df_all sok forrásoszlopot tartalmaz.
        A DB táblába csak az utolsó 9 feldolgozott oszlop kerül:
        bankszámlaszám, dátum, fájl, ID, típus, deviza, összeg, partner, számlaszám.
        """
        return self.df_all.iloc[:, -9:].copy()

    def validate_for_insert(self, df):
        """Ellenőrzi az adatok érvényességét DB-mentés előtt.

        Ellenőrzések:
          - Kötelező oszlopok megléte és kitöltöttsége
          - Fizetési dátum formátuma (yyyy.mm.dd)
          - Összeg konvertálhatósága számmá
          - típus mező értéke: minden sorban 'Szállító'
          - Deviza értéke: csak HUF/EUR/USD/GBP/CHF megengedett
        Hibás sorok piros háttérrel jelennek meg a táblázatban (PandasModel.set_invalid_rows).
        """
        required_columns = [
            "Számlaszám (formázott)",
            "Fizetési dátum",
            "Fizetési ID",
            "típus",
            "Deviza",
            "Összeg",
            "Partner neve",
            "Számlaszám",
        ]

        allowed_currencies = {"HUF", "EUR", "USD", "GBP", "CHF"}
        errors = []       # hibaüzenetek listája
        error_rows = set() # hibás DataFrame sor indexek halmaza

        # Üresség ellenőrzés: minden kötelező oszlopban minden sor ki kell legyen töltve
        for col in required_columns:
            invalid = df[df[col].isnull() | (df[col].astype(str).str.strip() == "")]
            if not invalid.empty:
                errors.append(f"Hiányzó érték a(z) '{col}' oszlopban.")
                error_rows.update(invalid.index)

        # Dátumformátum ellenőrzés
        try:
            pd.to_datetime(df["Fizetési dátum"], format="%Y.%m.%d", errors="raise")
        except Exception:
            errors.append(
                "A 'Fizetési dátum' mező nem megfelelő formátumú vagy hibás dátumot tartalmaz (pl. 2024.02.30)."
            )
            error_rows.update(df.index)

        # Összeg típusellenőrzés
        try:
            df["Összeg"].astype(str).str.replace(",", ".").astype(float)
        except Exception:
            errors.append("Az 'Összeg' mező nem konvertálható decimális számmá.")

        # Típus ellenőrzés
        invalid_type = df[df["típus"] != "Szállító"]
        if not invalid_type.empty:
            errors.append("A 'típus' mező minden sorban 'Szállító' kell legyen.")
            error_rows.update(invalid_type.index)

        # Deviza ellenőrzés
        invalid_currencies = df[~df["Deviza"].isin(allowed_currencies)]
        if not invalid_currencies.empty:
            errors.append(
                "A 'Deviza' mező csak az alábbi értékeket tartalmazhat: "
                + ", ".join(allowed_currencies)
            )
            error_rows.update(invalid_currencies.index)

        if errors:
            # Hibás sorok piros háttérrel jelölése a táblázatban
            model = self.table_view.model()
            if isinstance(model, PandasModel):
                model.set_invalid_rows(error_rows)
            self._error_rows = error_rows
            QMessageBox.warning(
                self,
                "Validációs hiba",
                "A következő hibák miatt nem lehet menteni:\n\n" + "\n".join(errors),
            )
            return False

        return True

    def run_database_save(self, df):
        """Elvégzi a tömeges adatbázis-mentést az IremsSzallito_stage táblába.

        Az oszlopokat Column1..Column9 névre nevezi át — a DB tábla
        oszlopai ilyen neveket várnak (vagy pozíció alapján veszi fel).
        """
        df = df.copy()
        df.columns = [f"Column{i}" for i in range(1, 10)]  # Column1..Column9
        success, message = self.db.insert_vendor_rows_bulk(df)
        self.hide_progress()

        if success:
            self.clear_data()  # sikeres mentés után UI visszaáll alapállapotba
            QMessageBox.information(self, "Siker", message)
        else:
            QMessageBox.critical(self, "Hiba", message)

    # -------------------------------------------------------------------------
    # clear_data override (extra állapot törlése)
    # -------------------------------------------------------------------------

    def clear_data(self):
        """Az alap törlés mellett törli a betöltött fájlok halmazát és a DataFrame-et."""
        super().clear_data()          # BaseImportView clear: fájllista, gombok reset
        self.loaded_files.clear()    # betöltött fájlok halmaza kiürítve
        self.df_all = pd.DataFrame() # üres DataFrame

    # -------------------------------------------------------------------------
    # Szállítói segédmetódusok
    # -------------------------------------------------------------------------

    def extract_iban(self, cell_text):
        """IBAN bankszámlaszám kinyerése az Information szöveges mezőből.

        Az IBAN formátuma: HU + 2 szám + 6x4 számjegy (pl. HU12 1234 5678 9012 3456 7800 0000)
        Csak a 'Beneficiary' szó ELŐTT keresi az IBAN-t (a kedvezményezett bankszámlája).
        """
        text = str(cell_text)
        # Megkeressük a 'Beneficiary' szó pozícióját — ez előtt kell az IBAN
        beneficiary_index = text.find("Beneficiary")
        if beneficiary_index == -1:
            return ""
        before_beneficiary = text[:beneficiary_index]
        # IBAN minta: HU + 2 számjegy, majd 4 számjegyű csoportok (opcionális szóköz)
        pattern = r"HU\d{2}(?:\s?\d{4}){6}"
        match = re.search(pattern, before_beneficiary)
        return match.group(0) if match else ""

    def format_hungarian_account_number(self, iban):
        """IBAN → rövid magyar bankszámlaszám formátum: DDDDDDDD-DDDDDDDD.

        Az IBAN első 4 karaktere (HUxx) az ország/ellenőrző szám —
        az utána következő 16 számjegy az érdemi bankszámlaszám.
        Formátum: első 8 jegy - következő 8 jegy.
        """
        match = re.search(r"HU\d{2}(\d{8})\s?(\d{8})", iban.replace(" ", ""))
        if match:
            return f"{match.group(1)}-{match.group(2)}"
        return ""

    def extract_partner_name(self, text: str) -> str:
        """Kedvezményezett (szállító) nevének kinyerése az Information mezőből.

        Az Information mező tipikus formátuma:
        "... Beneficiary: PARTNER NÉV Beneficiary Bank Acct: ..."
        A regex az első 'Beneficiary:' és a 'Beneficiary Bank Acct:' közötti részt veszi ki.
        """
        match = re.search(r"Beneficiary:\s*(.*?)\s*Beneficiary Bank Acct:", str(text))
        return match.group(1).strip() if match else ""

    def extract_payment_date(self, cell_text: str) -> str:
        """Fizetési dátum kinyerése a Status mezőből.

        A Status mező tipikus formátuma: "Executed 2024.03.15 ID: 123456"
        vagy "Submitted 2024.03.15 ID: 123456" vagy "Canceled 2024.03.15 ID: 123456"
        A regex keresi az állapotszó utáni YYYY.MM.DD formátumú dátumot.
        """
        match = re.search(
            r"(Executed|Submitted|Canceled)\s+(\d{4}\.\d{2}\.\d{2})", str(cell_text)
        )
        return match.group(2) if match else ""

    def extract_payment_id(self, cell_text: str) -> str:
        """Fizetési azonosító (ID) kinyerése a Status mezőből.

        Az ID a 'ID: ' prefix utáni számsorozat.
        Pl.: "Executed 2024.03.15 ID: 987654" → "987654"
        """
        match = re.search(r"ID:\s*(\d+)", str(cell_text))
        return match.group(1) if match else ""

    def expand_amount_paid(self, df):
        """Egy sorból több sort képez, ha az Amount Paid mezőben több összeg/deviza van.

        Az Irems export egyetlen cellában tárolhatja az összes fizetési tételt:
        pl. Amount Paid = "[1000 HUF, 500 EUR]"
            Payment Lines = "[Invoice ABC/2024/00001, Invoice DEF/2024/00002]"

        A függvény ezeket szétbontja és egyenként külön sorba helyezi:
          - sor 1: 1000 HUF, ABC/2024/00001
          - sor 2: 500 EUR, DEF/2024/00002

        zip_longest: ha a két lista különböző hosszú, a rövidebbik végét "" tölti ki.
        """
        rows = []
        # Szögletes zárójelek eltávolítása a listaszerű értékekből
        raw_amounts = df["Amount Paid"].fillna("").astype(str).str.strip("[]")
        raw_lines = df["Payment Lines"].fillna("").astype(str).str.strip("[]")

        for idx, (raw_amount, raw_line) in enumerate(zip(raw_amounts, raw_lines)):
            # Összeg + deviza párok keresése: pl. "1 234,56 HUF" vagy "-500 EUR"
            # Minta: szám (esetleg szóközzel, nem-törő szóközzel), vesszős tizedes, devizakód
            amount_matches = re.findall(
                r"(-?[\d\s\u00A0]+(?:,\d{2})?)\s*([A-Z]{3})", raw_amount
            )
            # Számlaszámok keresése: pl. "Invoice ABC/2024/00001"
            invoice_matches = re.findall(r"Invoice\s+(\S+)", raw_line)

            for (amount_raw, currency), invoice in zip_longest(
                amount_matches, invoice_matches, fillvalue=""
            ):
                # Szóközök és nem-törő szóközök eltávolítása az összegből
                amount = amount_raw.replace(" ", "").replace("\u00a0", "")
                row = df.iloc[idx]
                # Az eredeti sor összes mezőjét megtartjuk, és felülírjuk a számított értékeket
                rows.append(
                    {
                        **row.to_dict(),   # összes mező az eredeti sorból
                        "Deviza": currency,
                        "Összeg": amount,
                        "Számlaszám": invoice,
                    }
                )

        return pd.DataFrame(rows)
